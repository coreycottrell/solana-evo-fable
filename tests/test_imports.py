"""AS-IS + extract transplants must import under the new package name."""

from __future__ import annotations


def test_as_is_modules_import():
    from evobot import fees, jev_client, paths, price_backfill, price_pool

    assert price_pool.PricePool is not None
    assert price_backfill.backfill_all is not None
    assert jev_client.JevClient is not None
    assert fees.round_trip_fee_drag_bps is not None
    assert fees.fee_components is not None
    assert paths.data_dir is not None


def test_extract_modules_import():
    from evobot import baselines, evolution, strategies, vol_fit

    assert len(baselines.BASELINE_TEMPLATES) == 14
    assert evolution.crossover_params is not None
    assert evolution.ISLAND_NOISE_MULT
    assert strategies.signal_micro_trend is not None
    assert vol_fit.measure_tape is not None
    assert not hasattr(vol_fit, "score_vol_fit")
    assert not hasattr(vol_fit, "mutate_toward_vol_fit")
