"""Invariant 8: live/paper logs both arms (with-Jev and without-Jev)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from evobot.jev_client import JevClient
from evobot.jev_runtime import JevRuntime


def test_live_logs_both_arms(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EVO_BOT_JEV_MOCK", "1")
    client = JevClient(force_mock=True)
    rt = JevRuntime(tmp_path, client=client, sparse_every=1)
    prices = [100.0 + (i % 5) * 0.3 for i in range(50)]
    now = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    signals = [
        {
            "org_id": "org_a",
            "action": "BUY",
            "strength": 1.2,
            "reason": "test",
            "is_close": False,
        }
    ]
    out = rt.maybe_judge(
        now=now,
        prices=prices,
        symbol="SOL",
        poll_count=1,
        signals=signals,
        force=True,
    )
    assert out is not None
    assert "arm_with_jev" in out and out["arm_with_jev"]
    assert "arm_without_jev" in out and out["arm_without_jev"]
    assert out["arm_without_jev"]["policy"] == "numeric_signal"
    assert out["arm_with_jev"]["policy"] == "log_only_passthrough"
    # store row exists
    assert (tmp_path / "judgments" / "judgments.jsonl").exists()
    assert (tmp_path / "jev_ledger.jsonl").exists()
