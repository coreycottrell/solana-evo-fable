"""Invariant 1: exits are never gated (F1 — Jev/risk blocked stop-loss in v1)."""

from __future__ import annotations

import importlib.util

import pytest


def test_any_position_can_always_close():
    """Any size, any price, kill switch on, adversarial Jev — close must succeed.

    Documents F1 until the risk rewrite lands. Then this becomes a property test
    over the fill/reducer path.
    """
    risk_spec = importlib.util.find_spec("evobot.risk")
    broker_spec = importlib.util.find_spec("evobot.broker") or importlib.util.find_spec(
        "evobot.paper_broker"
    )
    if risk_spec is None or broker_spec is None:
        pytest.xfail(
            "risk/broker rewrite not landed — F1: v1 risk.check_order vetoed closes; "
            "v2 rule: risk blocks opens only; kill switch is reduce-only"
        )
    pytest.fail("risk/broker present but close-always property not implemented yet")
