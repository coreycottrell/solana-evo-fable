"""Judgment store keyed by (symbol, bar_ts, state_v, question_v, model_v)."""

from __future__ import annotations

from pathlib import Path

from evobot.jev_client import JevClient, JevResult, JevUsage
from evobot.judgment_store import JudgmentStore, make_store_key


def test_store_key_stable():
    a = make_store_key("SOL", "t1", "sv", "qv", "typesafe/jev-1.13")
    b = make_store_key("SOL", "t1", "sv", "qv", "typesafe/jev-1.13")
    c = make_store_key("SOL", "t2", "sv", "qv", "typesafe/jev-1.13")
    assert a == b and a != c


def test_append_and_get(tmp_path: Path):
    store = JudgmentStore(tmp_path)
    result = JevResult(
        model="typesafe/jev-1.13-mock",
        answers={"regime": {"type": "choice", "choice": "chaotic"}},
        usage=JevUsage(cost=0.0),
        mocked=True,
        id="mock-dec",
        provider="mock",
    )
    rec = store.record_from_result(
        result=result,
        symbol="SOL",
        bar_ts="2024-01-01T00:00:00+00:00",
        state_v="market_buckets_v1",
        question_v="core_v1",
        state={"ret_1": "flat"},
        arm_with_jev={"policy": "log_only_passthrough"},
        arm_without_jev={"policy": "numeric_signal"},
        trigger="signal",
    )
    got = store.get(
        symbol="SOL",
        bar_ts="2024-01-01T00:00:00+00:00",
        state_v="market_buckets_v1",
        question_v="core_v1",
        model_v="typesafe/jev-1.13-mock",
    )
    assert got is not None
    assert got.answers["regime"]["choice"] == "chaotic"
    assert store.stats["n_calls"] == 1
    assert store.stats["n_mocked"] == 1
