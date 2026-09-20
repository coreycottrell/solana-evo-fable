"""Invariant 4: real tape only — synthetic never enters the pool."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from evobot.price_pool import PricePool


def test_pool_rejects_synthetic_source(tmp_path: Path):
    pool = PricePool(tmp_path / "pool")
    ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="synthetic"):
        pool.append_tick("SOL", "mint", 100.0, source="synthetic", ts=ts)
    with pytest.raises(ValueError, match="synthetic"):
        pool.append_tick("SOL", "mint", 100.0, source="Synthetic", ts=ts)
    # Real source still accepted
    pool.append_tick("SOL", "mint", 100.0, source="jupiter", ts=ts)
    assert pool.tick_count("SOL") == 1
