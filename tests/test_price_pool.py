"""PricePool round-trip + sources= filter (F6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from evobot.price_pool import PricePool


def _fill(pool: PricePool, symbol: str, mint: str, n: int, *, source: str = "jupiter") -> None:
    t0 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    px = 100.0
    for i in range(n):
        px = px * (1.0 + (0.001 if i % 2 == 0 else -0.0008))
        pool.append_tick(symbol, mint, px, source=source, ts=t0 + timedelta(seconds=60 * i))


def test_append_and_load_mids(tmp_path: Path):
    pool = PricePool(tmp_path / "pool")
    _fill(pool, "SOL", "mint", 25)
    mids = pool.load_mids("SOL")
    assert len(mids) == 25
    assert mids[0] > 0
    bars = pool.load_bars("SOL", 60, n=10)
    assert len(bars) == 10
    assert "o" in bars[0] and "c" in bars[0]
    st = pool.stats(["SOL"])
    assert st["SOL"]["n"] == 25
    assert st["SOL"]["first"] is not None


def test_load_bars_sources_filter(tmp_path: Path):
    pool = PricePool(tmp_path / "pool")
    t0 = datetime(2024, 6, 1, tzinfo=timezone.utc)
    for i in range(10):
        src = "jupiter" if i % 2 == 0 else "coingecko"
        pool.append_tick(
            "SOL", "mint", 100.0 + i, source=src, ts=t0 + timedelta(seconds=60 * i)
        )
    all_bars = pool.load_bars("SOL", 60)
    jup_only = pool.load_bars("SOL", 60, sources=["jupiter"])
    assert len(all_bars) == 10
    assert len(jup_only) == 5
    empty = pool.load_bars("SOL", 60, sources=["binance"])
    assert empty == []


def test_append_requires_ts(tmp_path: Path):
    pool = PricePool(tmp_path / "pool")
    import pytest

    with pytest.raises(ValueError, match="requires ts"):
        pool.append_tick("SOL", "mint", 100.0, source="jupiter", ts=None)
