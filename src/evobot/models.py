"""Lean domain models — params only; no evaluation/graduation genes (inv 11)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


def new_id(prefix: str = "org") -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class ThesisType(str, Enum):
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    LIQUIDITY_FADE = "liquidity_fade"


class SideBias(str, Enum):
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class SignalAction(str, Enum):
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Signal:
    action: SignalAction = SignalAction.HOLD
    strength: float = 0.0
    reason: str = ""


@dataclass
class Genome:
    """Strategy params only — examiner/graduation genes are forbidden."""

    lookback: int = 20
    entry_threshold: float = 1.5
    exit_threshold: float = 0.3
    stop_loss_bps: float = 150.0
    take_profit_bps: float = 240.0
    cooldown_sec: int = 480
    size_usd: float = 100.0
    max_hold_sec: int = 7200
    side_bias: SideBias = SideBias.BOTH
    vol_filter_min: float = 0.0
    vol_filter_max: float = 1.0
    ema_fast: int = 5
    ema_slow: int = 20
    breakout_buffer_bps: float = 4.0
    fade_move_bps: float = 12.0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = v.value if isinstance(v, Enum) else v
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Genome":
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k not in known:
                continue
            if k == "side_bias":
                kwargs[k] = SideBias(v) if not isinstance(v, SideBias) else v
            else:
                kwargs[k] = v
        return cls(**kwargs)


@dataclass
class Position:
    mint: str = ""
    symbol: str = ""
    qty: float = 0.0
    avg_entry: float = 0.0
    opened_at: Optional[Any] = None  # datetime, injected
    side: str = "flat"  # long | short | flat


@dataclass
class WindowStats:
    """Cadence-window counters only (inv 12 — no lifetime stock in fitness)."""

    n_trades: int = 0
    realized_pnl: float = 0.0
    fees_usd: float = 0.0
    turnover_usd: float = 0.0


@dataclass
class Organism:
    thesis_type: ThesisType
    id: str = field(default_factory=lambda: new_id("org"))
    generation: int = 0
    label: str = ""
    genome: Genome = field(default_factory=Genome)
    cash_usd: float = 2000.0
    position: Position = field(default_factory=Position)
    realized_pnl: float = 0.0  # lifetime (display only)
    window: WindowStats = field(default_factory=WindowStats)
    last_trade_at: Optional[Any] = None
    last_signal: SignalAction = SignalAction.HOLD
    idle_cadences: int = 0
    parent_ids: tuple[str, ...] = ()

    def reset_window(self) -> None:
        self.window = WindowStats()
