"""Invariant 1: exits are never gated."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from evobot.broker import PaperBroker
from evobot.fees import FeesConfig
from evobot.models import Genome, Organism, Position, SignalAction, ThesisType
from evobot.risk import RiskConfig, RiskManager


def test_any_position_can_always_close(tmp_path: Path):
    kill = tmp_path / "KILL"
    kill.write_text("1")
    risk = RiskManager(
        RiskConfig(
            kill_switch_path=str(kill),
            max_notional_per_trade=1.0,  # would block opens
            max_position_usd=1.0,
            max_open_trades=0,
            max_stale_data_sec=0.0,
        )
    )
    broker = PaperBroker(risk, FeesConfig(), risk.config)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    org = Organism(
        thesis_type=ThesisType.MOMENTUM,
        genome=Genome(size_usd=100.0),
        cash_usd=50.0,
        position=Position(
            mint="m",
            symbol="SOL",
            qty=1.5,
            avg_entry=100.0,
            opened_at=now,
            side="long",
        ),
    )
    # Adversarial: kill on, notional caps tiny, stale — close must still fill
    fill = broker.execute(
        org,
        SignalAction.SELL,
        mid=90.0,
        symbol="SOL",
        mint="m",
        now=now,
        data_age_sec=9999.0,
        reason="stop",
    )
    assert fill is not None
    assert fill.is_close
    assert org.position.qty == 0.0


def test_risk_blocks_open_when_kill_on(tmp_path: Path):
    kill = tmp_path / "KILL"
    kill.write_text("1")
    risk = RiskManager(RiskConfig(kill_switch_path=str(kill)))
    broker = PaperBroker(risk, FeesConfig(), risk.config)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    org = Organism(thesis_type=ThesisType.MOMENTUM, cash_usd=2000.0)
    fill = broker.execute(
        org, SignalAction.BUY, mid=100.0, symbol="SOL", mint="m", now=now
    )
    assert fill is None
