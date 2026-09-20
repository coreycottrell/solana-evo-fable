"""Content-addressed judgment store — keyed by (symbol, bar_ts, state_v, question_v, model_v).

Append-only JSONL under ``data/judgments/``. One call serves every consumer
(MISSION judgment store + inv 7/8 logging).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from evobot.jev_client import JevResult

log = logging.getLogger(__name__)

JUDGMENTS_SUBDIR = "judgments"
LEDGER_NAME = "jev_ledger.jsonl"
LAST_NAME = "jev_last.json"
STATS_NAME = "jev_stats.json"


@dataclass
class JudgmentRecord:
    symbol: str
    bar_ts: str
    state_v: str
    question_v: str
    model_v: str
    state: dict[str, Any]
    answers: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    mocked: bool = False
    decision_id: str = ""
    provider: str = ""
    state_fp: str = ""
    # Both arms placeholders for Premium (inv 8) — never gates exits.
    arm_with_jev: dict[str, Any] = field(default_factory=dict)
    arm_without_jev: dict[str, Any] = field(default_factory=dict)
    trigger: str = ""  # "signal" | "sparse" | "jev_once"

    def store_key(self) -> str:
        return make_store_key(
            self.symbol, self.bar_ts, self.state_v, self.question_v, self.model_v
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key"] = self.store_key()
        return d


def make_store_key(
    symbol: str,
    bar_ts: str,
    state_v: str,
    question_v: str,
    model_v: str,
) -> str:
    raw = f"{symbol}|{bar_ts}|{state_v}|{question_v}|{model_v}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class JudgmentStore:
    """JSONL judgment store + last/stats sidecar for the dashboard."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / JUDGMENTS_SUBDIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "judgments.jsonl"
        self.ledger_path = self.data_dir / LEDGER_NAME
        self.last_path = self.data_dir / LAST_NAME
        self.stats_path = self.data_dir / STATS_NAME
        self._index: dict[str, JudgmentRecord] = {}
        self._load_index()
        self.stats = self._load_stats()

    def _load_index(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = row.get("key") or make_store_key(
                        row.get("symbol", ""),
                        row.get("bar_ts", ""),
                        row.get("state_v", ""),
                        row.get("question_v", ""),
                        row.get("model_v", ""),
                    )
                    self._index[key] = JudgmentRecord(
                        symbol=str(row.get("symbol") or ""),
                        bar_ts=str(row.get("bar_ts") or ""),
                        state_v=str(row.get("state_v") or ""),
                        question_v=str(row.get("question_v") or ""),
                        model_v=str(row.get("model_v") or ""),
                        state=dict(row.get("state") or {}),
                        answers=dict(row.get("answers") or {}),
                        usage=dict(row.get("usage") or {}),
                        mocked=bool(row.get("mocked")),
                        decision_id=str(row.get("decision_id") or ""),
                        provider=str(row.get("provider") or ""),
                        state_fp=str(row.get("state_fp") or ""),
                        arm_with_jev=dict(row.get("arm_with_jev") or {}),
                        arm_without_jev=dict(row.get("arm_without_jev") or {}),
                        trigger=str(row.get("trigger") or ""),
                    )
        except OSError as exc:
            log.warning("judgment index load failed: %s", exc)

    def _load_stats(self) -> dict[str, Any]:
        if self.stats_path.exists():
            try:
                return json.loads(self.stats_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "n_calls": 0,
            "n_mocked": 0,
            "n_live": 0,
            "n_cache_hits": 0,
            "total_cost": 0.0,
            "last_model": "",
            "last_mocked": True,
            "last_bar_ts": "",
            "last_trigger": "",
        }

    def _save_stats(self) -> None:
        self.stats_path.write_text(
            json.dumps(self.stats, indent=2, default=str) + "\n", encoding="utf-8"
        )

    def get(
        self,
        *,
        symbol: str,
        bar_ts: str,
        state_v: str,
        question_v: str,
        model_v: str,
    ) -> Optional[JudgmentRecord]:
        key = make_store_key(symbol, bar_ts, state_v, question_v, model_v)
        return self._index.get(key)

    def append(self, rec: JudgmentRecord, *, from_cache: bool = False) -> JudgmentRecord:
        row = rec.to_dict()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        self._index[rec.store_key()] = rec
        self.last_path.write_text(
            json.dumps(
                {
                    "model": rec.model_v,
                    "mocked": rec.mocked,
                    "answers": rec.answers,
                    "usage": rec.usage,
                    "id": rec.decision_id,
                    "provider": rec.provider,
                    "symbol": rec.symbol,
                    "bar_ts": rec.bar_ts,
                    "state_v": rec.state_v,
                    "question_v": rec.question_v,
                    "arm_with_jev": rec.arm_with_jev,
                    "arm_without_jev": rec.arm_without_jev,
                    "trigger": rec.trigger,
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        if from_cache:
            self.stats["n_cache_hits"] = int(self.stats.get("n_cache_hits") or 0) + 1
        else:
            self.stats["n_calls"] = int(self.stats.get("n_calls") or 0) + 1
            if rec.mocked:
                self.stats["n_mocked"] = int(self.stats.get("n_mocked") or 0) + 1
            else:
                self.stats["n_live"] = int(self.stats.get("n_live") or 0) + 1
            cost = float((rec.usage or {}).get("cost") or 0.0)
            self.stats["total_cost"] = float(self.stats.get("total_cost") or 0.0) + cost
        self.stats["last_model"] = rec.model_v
        self.stats["last_mocked"] = rec.mocked
        self.stats["last_bar_ts"] = rec.bar_ts
        self.stats["last_trigger"] = rec.trigger
        self._save_stats()
        return rec

    def record_from_result(
        self,
        *,
        result: JevResult,
        symbol: str,
        bar_ts: str,
        state_v: str,
        question_v: str,
        state: dict[str, Any],
        state_fp: str = "",
        arm_with_jev: Optional[dict[str, Any]] = None,
        arm_without_jev: Optional[dict[str, Any]] = None,
        trigger: str = "",
    ) -> JudgmentRecord:
        rec = JudgmentRecord(
            symbol=symbol,
            bar_ts=bar_ts,
            state_v=state_v,
            question_v=question_v,
            model_v=result.model,
            state=state,
            answers=result.answers,
            usage={
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost": result.usage.cost,
            },
            mocked=result.mocked,
            decision_id=result.id,
            provider=result.provider,
            state_fp=state_fp,
            arm_with_jev=dict(arm_with_jev or {}),
            arm_without_jev=dict(arm_without_jev or {}),
            trigger=trigger,
        )
        return self.append(rec)

    def snapshot_stats(self) -> dict[str, Any]:
        last: dict[str, Any] = {}
        if self.last_path.exists():
            try:
                last = json.loads(self.last_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                last = {}
        return {
            **self.stats,
            "last_answers": last.get("answers") or {},
            "last_arm_with_jev": last.get("arm_with_jev") or {},
            "last_arm_without_jev": last.get("arm_without_jev") or {},
        }
