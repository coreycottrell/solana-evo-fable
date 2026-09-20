"""Orchestrate market-only Jev calls for the paper loop (log-only; inv 1/6/8).

Does NOT gate exits. Does NOT size from Score magnitudes. Logs both arms
(with-Jev vs without-Jev placeholders) for future Premium.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from evobot.jev_client import DEFAULT_MODEL, JevClient, JevError, JevResult
from evobot.judgment_store import JudgmentStore
from evobot.questions import QUESTION_SET, QUESTION_V, questions_for_api
from evobot.state_encoder import STATE_V, encode_market_state, state_fingerprint

log = logging.getLogger(__name__)

SPARSE_EVERY_N_POLLS = 10


class JevRuntime:
    def __init__(
        self,
        data_dir: Path,
        *,
        client: Optional[JevClient] = None,
        model: str = DEFAULT_MODEL,
        sparse_every: int = SPARSE_EVERY_N_POLLS,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.store = JudgmentStore(self.data_dir)
        self.client = client or JevClient(model=model, project_root=self.data_dir.parent)
        self.sparse_every = max(1, int(sparse_every))
        self.last_result: Optional[JevResult] = None
        self.last_record: Optional[Any] = None

    def maybe_judge(
        self,
        *,
        now: datetime,
        prices: Sequence[float],
        symbol: str,
        poll_count: int,
        signals: Sequence[dict[str, Any]],
        force: bool = False,
        trigger: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Call Jev on signal or sparse schedule; always log-only.

        ``signals``: list of {org_id, action, strength, reason, is_close}.
        """
        non_hold = [s for s in signals if str(s.get("action") or "HOLD") != "HOLD"]
        sparse = poll_count > 0 and (poll_count % self.sparse_every == 1)
        if not force and not non_hold and not sparse:
            return None

        if trigger is None:
            if force:
                trigger = "jev_once"
            elif non_hold:
                trigger = "signal"
            else:
                trigger = "sparse"

        state = encode_market_state(prices)
        state_fp = state_fingerprint(state)
        bar_ts = now.isoformat()
        model_v = self.client.model  # pin before call; result.model may append date
        qs = questions_for_api(QUESTION_SET)

        # Cache key uses pinned allowlist model id (not dated response model).
        cached = self.store.get(
            symbol=symbol,
            bar_ts=bar_ts,
            state_v=STATE_V,
            question_v=QUESTION_V,
            model_v=model_v,
        )
        # bar_ts is unique per poll clock → cache rarely hits live; still correct for replay.
        if cached is not None and not force:
            self.store.stats["n_cache_hits"] = int(self.store.stats.get("n_cache_hits") or 0) + 1
            self.store._save_stats()
            self.last_record = cached
            return cached.to_dict()

        arm_without = _arm_without_jev(non_hold or list(signals))
        # Placeholder with-Jev arm: same actions logged; future Premium compares
        # a learned combiner. Never used to gate exits (inv 1).
        arm_with = {
            "policy": "log_only_passthrough",
            "note": "Jev answers are features; no gate / no size from Score (inv 6)",
            "signals": list(non_hold or signals),
            "answers_summary": {},
        }

        try:
            result = self.client.decide(state, qs)
        except JevError as exc:
            log.warning("Jev call failed (%s); skipping store write", exc)
            return {"error": str(exc), "trigger": trigger, "mocked": None}

        arm_with["answers_summary"] = {
            qid: _compact_answer(ans) for qid, ans in (result.answers or {}).items()
        }
        self.last_result = result
        rec = self.store.record_from_result(
            result=result,
            symbol=symbol,
            bar_ts=bar_ts,
            state_v=STATE_V,
            question_v=QUESTION_V,
            state=state,
            state_fp=state_fp,
            arm_with_jev=arm_with,
            arm_without_jev=arm_without,
            trigger=trigger,
        )
        self.last_record = rec
        log.info(
            "jev %s model=%s mocked=%s cost=%.6g answers=%s",
            trigger,
            result.model,
            result.mocked,
            result.usage.cost,
            list(result.answers.keys()),
        )
        return rec.to_dict()

    def stats_for_snapshot(self) -> dict[str, Any]:
        return self.store.snapshot_stats()


def _compact_answer(ans: Any) -> dict[str, Any]:
    if not isinstance(ans, dict):
        return {"raw": ans}
    t = ans.get("type")
    out: dict[str, Any] = {"type": t}
    if "noul" in ans:
        out["noul"] = ans.get("noul")
    if "choice" in ans:
        out["choice"] = ans.get("choice")
        out["confidence"] = ans.get("confidence")
    if "score" in ans:
        out["score"] = ans.get("score")
        out["confidence"] = ans.get("confidence")
    return out


def _arm_without_jev(signals: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Numeric-only baseline arm — what the colony would do without Jev."""
    return {
        "policy": "numeric_signal",
        "signals": [
            {
                "org_id": s.get("org_id"),
                "action": s.get("action"),
                "strength": s.get("strength"),
                "is_close": s.get("is_close"),
                "reason": s.get("reason"),
            }
            for s in signals
        ],
    }


def run_jev_once(
    *,
    data_dir: Path,
    prices: Sequence[float],
    now: datetime,
    symbol: str = "SOL",
    force_mock: Optional[bool] = None,
) -> dict[str, Any]:
    """One market-only Decisions call. ``now`` must be injected (inv 2)."""
    client = JevClient(project_root=Path(data_dir).parent, force_mock=force_mock)
    rt = JevRuntime(data_dir, client=client)
    out = rt.maybe_judge(
        now=now,
        prices=prices,
        symbol=symbol,
        poll_count=1,
        signals=[],
        force=True,
        trigger="jev_once",
    )
    return out or {}
