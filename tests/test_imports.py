"""AS-IS transplants must import under the new package name."""

from __future__ import annotations


def test_as_is_modules_import():
    from evobot import fees, jev_client, paths, price_backfill, price_pool

    assert price_pool.PricePool is not None
    assert price_backfill.backfill_all is not None
    assert jev_client.JevClient is not None
    assert fees.round_trip_fee_drag_bps is not None
    assert paths.data_dir is not None
