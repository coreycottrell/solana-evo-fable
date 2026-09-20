"""Jev client allowlist + mock path — transplanted from v1 test_jev.py (leaf only)."""

from __future__ import annotations

import pytest

from evobot.jev_client import (
    ALLOWED_MODELS,
    JevClient,
    JevModelNotAllowed,
    assert_model_allowed,
)


def test_allowlist_accepts_pin_and_latest():
    assert assert_model_allowed("typesafe/jev-1.13") == "typesafe/jev-1.13"
    assert assert_model_allowed("~typesafe/jev-latest") == "~typesafe/jev-latest"
    assert ALLOWED_MODELS == frozenset({"typesafe/jev-1.13", "~typesafe/jev-latest"})


def test_allowlist_rejects_other_models():
    with pytest.raises(JevModelNotAllowed):
        assert_model_allowed("openai/gpt-4o")
    with pytest.raises(JevModelNotAllowed):
        JevClient(model="anthropic/claude-3.5-sonnet", force_mock=True)


def test_mock_decide_deterministic_no_network(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("EVO_BOT_JEV_MOCK", "1")
    client = JevClient(force_mock=True)
    state = {"regime": "test", "px_bucket": "mid"}
    qs = {
        "toxic_flow": {"type": "noul", "prompt": "toxic?"},
        "setup_quality": {"type": "score", "prompt": "setup?"},
    }
    r1 = client.decide(state, qs)
    r2 = client.decide(state, qs)
    assert r1.mocked and r2.mocked
    assert r1.answers.keys() == qs.keys()
    assert r1.answers == r2.answers
    assert "toxic_flow" in r1.answers
    assert r1.answers["toxic_flow"]["type"] == "noul"
