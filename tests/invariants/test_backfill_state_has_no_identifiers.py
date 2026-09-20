"""Invariant 7: market-only / backfill state has no identifiers."""

from __future__ import annotations

import pytest

from evobot.state_encoder import (
    FORBIDDEN_STATE_KEYS,
    assert_backfill_state_clean,
    encode_market_state,
)


def test_backfill_state_has_no_identifiers():
    prices = [100.0 + i * 0.1 for i in range(60)]
    state = encode_market_state(prices)
    assert state["state_v"]
    assert state["tape"] == "ok"
    for key in FORBIDDEN_STATE_KEYS:
        assert key not in state
    # no absolute prices / numerics
    for k, v in state.items():
        if k == "state_v":
            continue
        assert isinstance(v, str), f"{k} should be named bucket str, got {type(v)}"
    assert_backfill_state_clean(state)


def test_backfill_state_rejects_smuggled_identifiers():
    with pytest.raises(ValueError):
        assert_backfill_state_clean({"regime": "x", "symbol": "SOL"})
    with pytest.raises(ValueError):
        assert_backfill_state_clean({"px": 100.0})
