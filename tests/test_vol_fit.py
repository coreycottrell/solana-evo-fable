"""Tape metrics extract — measure only (no score/mutate)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from evobot.price_pool import PricePool
from evobot.vol_fit import (
    TapeMetrics,
    _atr_like_bps,
    _percentile,
    measure_tape,
)


def test_percentile_interpolation():
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert _percentile([], 50) == 0.0
    assert _percentile([7.0], 90) == 7.0


def test_measure_tape_from_pool(tmp_path: Path):
    pool = PricePool(tmp_path / "pool")
    t0 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    px = 100.0
    for i in range(120):
        px *= 1.001 if i % 2 == 0 else 0.999
        pool.append_tick("SOL", "mint", px, source="jupiter", ts=t0 + timedelta(seconds=60 * i))
    m = measure_tape(pool, "SOL", min_bars_1m=60)
    assert isinstance(m, TapeMetrics)
    assert not m.insufficient
    assert m.n_bars_1m >= 60
    assert m.abs_ret_1m_p50_bps > 0
    assert m.atr_1m_bps >= 0
    assert "score_vol_fit" not in dir(__import__("evobot.vol_fit", fromlist=["*"]))


def test_atr_like_on_bars():
    bars = [
        {"h": 101.0, "l": 99.0, "c": 100.0},
        {"h": 102.0, "l": 100.0, "c": 101.0},
        {"h": 103.0, "l": 100.5, "c": 102.0},
    ]
    atr = _atr_like_bps(bars, period=2)
    assert atr > 0
