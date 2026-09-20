"""Paper colony engine — all time via injected ``now``."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from evobot.broker import PaperBroker
from evobot.evolution import (
    EvolutionConfig,
    seed_colony,
    select_retire_target,
    spawn_child,
)
from evobot.evolution import build_heritage, island_for_thesis
from evobot.fees import FeesConfig, passes_min_edge_gate, round_trip_fee_drag_bps
from evobot.fitness import rank_population, reset_cadence_windows, window_fitness
from evobot.models import Organism, SignalAction
from evobot.risk import RiskConfig, RiskManager
from evobot.strategies import generate_signal
from evobot.jev_runtime import JevRuntime

log = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class PaperState:
    organisms: list[Organism] = field(default_factory=list)
    cadence_index: int = 0
    cadence_started_at: Optional[datetime] = None
    last_step_at: Optional[datetime] = None
    generation_max: int = 0
    n_evolves: int = 0
    n_fills: int = 0
    last_evolve: Optional[dict[str, Any]] = None
    poll_count: int = 0
    jev_calls: int = 0
    last_jev: Optional[dict[str, Any]] = None


class PaperEngine:
    def __init__(
        self,
        *,
        data_dir: Path,
        n_organisms: int = 8,
        cadence_sec: float = 14400.0,
        evo_cfg: Optional[EvolutionConfig] = None,
        risk_cfg: Optional[RiskConfig] = None,
        fees: Optional[FeesConfig] = None,
        rng_seed: int = 42,
    ) -> None:
        import random

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cadence_sec = float(cadence_sec)
        self.evo_cfg = evo_cfg or EvolutionConfig()
        self.risk_cfg = risk_cfg or RiskConfig(
            kill_switch_path=str(self.data_dir / "KILL")
        )
        self.fees = fees or FeesConfig()
        self.risk = RiskManager(self.risk_cfg)
        self.broker = PaperBroker(self.risk, self.fees, self.risk_cfg)
        self.rng = random.Random(rng_seed)
        self.state = PaperState(organisms=seed_colony(n_organisms, starting_cash=self.evo_cfg.starting_cash))
        self.jev = JevRuntime(self.data_dir)
        self.pop_path = self.data_dir / "population.json"
        self.cadence_log = self.data_dir / "cadences.jsonl"
        self.trades_log = self.data_dir / "trades.jsonl"
        self._load_or_save()

    def _load_or_save(self) -> None:
        if self.pop_path.exists():
            try:
                self._load()
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("population load failed (%s); reseeding", exc)
        self._save()

    def _save(self) -> None:
        payload = {
            "cadence_index": self.state.cadence_index,
            "n_evolves": self.state.n_evolves,
            "n_fills": self.state.n_fills,
            "generation_max": self.state.generation_max,
            "last_evolve": self.state.last_evolve,
            "poll_count": self.state.poll_count,
            "cadence_started_at": self.state.cadence_started_at.isoformat()
            if self.state.cadence_started_at
            else None,
            "organisms": [_org_to_dict(o) for o in self.state.organisms],
        }
        tmp = self.pop_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(self.pop_path)

    def _load(self) -> None:
        from evobot.models import Genome, Position, ThesisType, WindowStats

        raw = json.loads(self.pop_path.read_text(encoding="utf-8"))
        orgs: list[Organism] = []
        for row in raw.get("organisms") or []:
            g = Genome.from_dict(row.get("genome") or {})
            pos_raw = row.get("position") or {}
            opened = pos_raw.get("opened_at")
            if isinstance(opened, str):
                opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            wraw = row.get("window") or {}
            orgs.append(
                Organism(
                    id=row["id"],
                    thesis_type=ThesisType(row["thesis_type"]),
                    generation=int(row.get("generation") or 0),
                    label=row.get("label") or "",
                    genome=g,
                    cash_usd=float(row.get("cash_usd") or 2000.0),
                    position=Position(
                        mint=pos_raw.get("mint") or "",
                        symbol=pos_raw.get("symbol") or "",
                        qty=float(pos_raw.get("qty") or 0.0),
                        avg_entry=float(pos_raw.get("avg_entry") or 0.0),
                        opened_at=opened,
                        side=pos_raw.get("side") or "flat",
                    ),
                    realized_pnl=float(row.get("realized_pnl") or 0.0),
                    window=WindowStats(
                        n_trades=int(wraw.get("n_trades") or 0),
                        realized_pnl=float(wraw.get("realized_pnl") or 0.0),
                        fees_usd=float(wraw.get("fees_usd") or 0.0),
                        turnover_usd=float(wraw.get("turnover_usd") or 0.0),
                    ),
                    idle_cadences=int(row.get("idle_cadences") or 0),
                    parent_ids=tuple(row.get("parent_ids") or ()),
                )
            )
        self.state.organisms = orgs
        self.state.cadence_index = int(raw.get("cadence_index") or 0)
        self.state.n_evolves = int(raw.get("n_evolves") or 0)
        self.state.n_fills = int(raw.get("n_fills") or 0)
        self.state.generation_max = int(raw.get("generation_max") or 0)
        self.state.last_evolve = raw.get("last_evolve")
        self.state.poll_count = int(raw.get("poll_count") or 0)
        cs = raw.get("cadence_started_at")
        if cs:
            self.state.cadence_started_at = datetime.fromisoformat(str(cs).replace("Z", "+00:00"))

    def step(
        self,
        now: datetime,
        prices: Sequence[float],
        *,
        mid: Optional[float] = None,
        symbol: str = "SOL",
        mint: str = SOL_MINT,
        data_age_sec: float = 0.0,
    ) -> dict[str, Any]:
        """One poll tick with injected ``now``."""
        if self.state.cadence_started_at is None:
            self.state.cadence_started_at = now
        mid = float(mid if mid is not None else (prices[-1] if prices else 0.0))
        fills_this = 0
        open_count = sum(1 for o in self.state.organisms if o.position.qty != 0)

        signal_rows: list[dict[str, Any]] = []
        for org in self.state.organisms:
            sig = generate_signal(org, prices, now)
            org.last_signal = sig.action
            is_close = (org.position.qty > 0 and sig.action == SignalAction.SELL) or (
                org.position.qty < 0 and sig.action == SignalAction.BUY
            )
            if sig.action != SignalAction.HOLD:
                signal_rows.append(
                    {
                        "org_id": org.id,
                        "action": sig.action.value,
                        "strength": sig.strength,
                        "reason": sig.reason,
                        "is_close": is_close,
                    }
                )
            if sig.action == SignalAction.HOLD:
                continue
            # Inv 1: closes are never gated by edge / Jev. Opens may soft-skip on fees.
            if not is_close and not passes_min_edge_gate(
                size_usd=org.genome.size_usd, strength=sig.strength, fees=self.fees
            ):
                continue
            fill = self.broker.execute(
                org,
                sig.action,
                mid=mid,
                symbol=symbol,
                mint=mint,
                now=now,
                data_age_sec=data_age_sec,
                reason=sig.reason,
                open_trade_count=open_count,
            )
            if fill is not None:
                fills_this += 1
                self.state.n_fills += 1
                open_count = sum(1 for o in self.state.organisms if o.position.qty != 0)
                self._log_trade(org, fill, mid)

        self.state.poll_count += 1
        # Log-only Jev: on signal or sparse. Never gates exits / never sizes from Score.
        jev_info = self.jev.maybe_judge(
            now=now,
            prices=prices,
            symbol=symbol,
            poll_count=self.state.poll_count,
            signals=signal_rows,
        )
        if jev_info and not jev_info.get("error"):
            self.state.jev_calls += 1
            self.state.last_jev = {
                "model": jev_info.get("model_v"),
                "mocked": jev_info.get("mocked"),
                "trigger": jev_info.get("trigger"),
                "bar_ts": jev_info.get("bar_ts"),
                "answers": jev_info.get("answers"),
                "arm_with_jev": jev_info.get("arm_with_jev"),
                "arm_without_jev": jev_info.get("arm_without_jev"),
                "cost": (jev_info.get("usage") or {}).get("cost"),
            }
        self.state.last_step_at = now
        evolved = None
        elapsed = (now - self.state.cadence_started_at).total_seconds()
        if elapsed >= self.cadence_sec:
            evolved = self._evolve(now)
        self._save()
        return {
            "poll": self.state.poll_count,
            "fills": fills_this,
            "mid": mid,
            "cadence_index": self.state.cadence_index,
            "elapsed_sec": elapsed,
            "evolved": evolved,
            "n_organisms": len(self.state.organisms),
            "jev": self.state.last_jev if jev_info else None,
        }

    def _evolve(self, now: datetime) -> dict[str, Any]:
        ranked = rank_population(self.state.organisms)
        # bump idle counters
        for org, _ in ranked:
            if org.window.n_trades == 0:
                org.idle_cadences += 1
            else:
                org.idle_cadences = 0

        victim, vscore, why = select_retire_target(
            ranked, idle_retire_cadences=self.evo_cfg.idle_retire_cadences
        )
        top2 = [ranked[0][0], ranked[1][0]] if len(ranked) >= 2 else [ranked[0][0], ranked[0][0]]
        child = spawn_child(top2[0], top2[1], cfg=self.evo_cfg, rng=self.rng)
        heritage = getattr(child, "heritage", None) or build_heritage(top2[0], top2[1])

        # replace victim
        self.state.organisms = [o for o in self.state.organisms if o.id != victim.id] + [child]
        self.state.generation_max = max(self.state.generation_max, child.generation)
        self.state.n_evolves += 1
        self.state.cadence_index += 1

        report = {
            "cadence": self.state.cadence_index,
            "at": now.isoformat(),
            "retired": {"id": victim.id, "label": victim.label, "score": vscore, "why": why},
            "parents": [top2[0].id, top2[1].id],
            "heritage": heritage,
            "child": {"id": child.id, "label": child.label, "thesis": child.thesis_type.value, "gen": child.generation},
            "ranked": [
                {"id": o.id, "label": o.label, "fitness": s, "window_pnl": o.window.realized_pnl, "n_trades": o.window.n_trades}
                for o, s in ranked
            ],
        }
        self.state.last_evolve = report
        with open(self.cadence_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, default=str) + "\n")
        reset_cadence_windows(self.state.organisms)
        self.state.cadence_started_at = now
        log.info(
            "evolve cadence=%s retire=%s(%s) child=%s gen=%s",
            self.state.cadence_index,
            victim.label,
            why,
            child.label,
            child.generation,
        )
        return report

    def _log_trade(self, org: Organism, fill: Any, mid: float) -> None:
        row = {
            "ts": fill.ts.isoformat(),
            "org": org.id,
            "label": org.label,
            "thesis": org.thesis_type.value,
            "side": fill.side,
            "qty": fill.qty,
            "price": fill.price,
            "mid": mid,
            "fee": fill.fee_usd,
            "pnl": fill.pnl_usd,
            "close": fill.is_close,
            "reason": fill.reason,
        }
        with open(self.trades_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def snapshot(self) -> dict[str, Any]:
        from evobot.dashboard import theory_body, theory_bullets

        ranked = rank_population(self.state.organisms)
        rt_ref = round_trip_fee_drag_bps(100.0, self.fees)
        rows = []
        for o, _ in ranked:
            g = o.genome.to_dict()
            row = {
                "id": o.id,
                "label": o.label,
                "thesis": o.thesis_type.value,
                "island": island_for_thesis(o.thesis_type),
                "generation": o.generation,
                "fitness": window_fitness(o),
                "window_pnl": o.window.realized_pnl,
                "window_trades": o.window.n_trades,
                "lifetime_pnl": o.realized_pnl,
                "cash": o.cash_usd,
                "pos_qty": o.position.qty,
                "idle_cadences": o.idle_cadences,
                "last_signal": o.last_signal.value if hasattr(o.last_signal, "value") else str(o.last_signal),
                "size_usd": o.genome.size_usd,
                "round_trip_fee_bps": round_trip_fee_drag_bps(o.genome.size_usd, self.fees),
                "genome": g,
                "parent_ids": list(o.parent_ids),
            }
            row["theory_bullets"] = theory_bullets(row)
            row["theory_body"] = theory_body(row)
            rows.append(row)
        jev_stats = self.jev.stats_for_snapshot()
        return {
            "cadence_index": self.state.cadence_index,
            "n_evolves": self.state.n_evolves,
            "n_fills": self.state.n_fills,
            "poll_count": self.state.poll_count,
            "generation_max": self.state.generation_max,
            "cadence_sec": self.cadence_sec,
            "round_trip_fee_bps_ref": rt_ref,
            "cadence_started_at": self.state.cadence_started_at.isoformat()
            if self.state.cadence_started_at
            else None,
            "last_step_at": self.state.last_step_at.isoformat() if self.state.last_step_at else None,
            "last_evolve": self.state.last_evolve,
            "organisms": rows,
            "jev_calls": self.state.jev_calls,
            "last_jev": self.state.last_jev,
            "jev": jev_stats,
        }


def _org_to_dict(o: Organism) -> dict[str, Any]:
    pos = o.position
    return {
        "id": o.id,
        "thesis_type": o.thesis_type.value,
        "generation": o.generation,
        "label": o.label,
        "genome": o.genome.to_dict(),
        "cash_usd": o.cash_usd,
        "position": {
            "mint": pos.mint,
            "symbol": pos.symbol,
            "qty": pos.qty,
            "avg_entry": pos.avg_entry,
            "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
            "side": pos.side,
        },
        "realized_pnl": o.realized_pnl,
        "window": {
            "n_trades": o.window.n_trades,
            "realized_pnl": o.window.realized_pnl,
            "fees_usd": o.window.fees_usd,
            "turnover_usd": o.window.turnover_usd,
        },
        "idle_cadences": o.idle_cadences,
        "parent_ids": list(o.parent_ids),
    }
