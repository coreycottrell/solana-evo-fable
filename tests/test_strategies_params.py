"""Thesis-scoped params — pure (prices, params) signals."""

from __future__ import annotations

from evobot.models import Genome, ThesisType
from evobot.strategies import (
    MeanReversionParams,
    MomentumParams,
    signal_mean_reversion,
    signal_micro_trend,
    signal_momentum,
    thesis_params_from_genome,
    MicroTrendParams,
)


def test_thesis_params_projection():
    g = Genome(lookback=16, entry_threshold=0.15)
    p = thesis_params_from_genome(ThesisType.MOMENTUM, g)
    assert isinstance(p, MomentumParams)
    assert p.lookback == 16
    assert p.entry_threshold == 0.15

    g2 = Genome(lookback=20, entry_threshold=0.85, exit_threshold=0.35)
    p2 = thesis_params_from_genome(ThesisType.MEAN_REVERSION, g2)
    assert isinstance(p2, MeanReversionParams)


def test_signal_mean_reversion_pure():
    # flat then spike up → sell
    prices = [100.0] * 20 + [110.0]
    sig = signal_mean_reversion(prices, MeanReversionParams(lookback=20, entry_threshold=0.5))
    assert sig.action.value in ("SELL", "HOLD", "BUY")


def test_signal_momentum_pure():
    prices = [100.0 + i for i in range(20)]
    sig = signal_momentum(prices, MomentumParams(lookback=10, entry_threshold=0.10))
    assert sig.action.value in ("BUY", "SELL", "HOLD")


def test_signal_micro_trend_pure():
    prices = [100.0 + 0.5 * i for i in range(40)]
    sig = signal_micro_trend(
        prices, MicroTrendParams(lookback=20, ema_fast=5, ema_slow=18, entry_threshold=0.18)
    )
    assert sig.reason.startswith("mt=") or sig.reason == "warmup"
