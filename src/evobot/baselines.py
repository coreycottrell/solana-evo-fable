"""14 baseline templates mined from v1 population TREND_SEEDS + CONTRARIAN_SEEDS.

Strategy/risk params only — no Jev, Twitter, or graduation genes (inv 11 / F12).
These are the deterministic denominator for label-factory / fee-clearing checks.
"""

from __future__ import annotations

from typing import Any

from evobot.models import Genome, Organism, SideBias, ThesisType, new_id

# (island, label, thesis, strategy overrides)
BASELINE_TEMPLATES: list[tuple[str, str, ThesisType, dict[str, Any]]] = [
    # --- trend island (7) ---
    (
        "trend",
        "momentum",
        ThesisType.MOMENTUM,
        dict(
            lookback=16,
            entry_threshold=0.15,
            exit_threshold=0.08,
            stop_loss_bps=150.0,
            take_profit_bps=240.0,
            cooldown_sec=480,
            size_usd=100.0,
            max_hold_sec=7200,
            side_bias=SideBias.LONG,
            vol_filter_min=0.0,
            vol_filter_max=0.05,
        ),
    ),
    (
        "trend",
        "momentum_fast",
        ThesisType.MOMENTUM,
        dict(
            lookback=8,
            entry_threshold=0.10,
            exit_threshold=0.05,
            stop_loss_bps=120.0,
            take_profit_bps=190.0,
            cooldown_sec=300,
            size_usd=90.0,
            max_hold_sec=3600,
            side_bias=SideBias.LONG,
            vol_filter_min=0.0,
            vol_filter_max=0.08,
        ),
    ),
    (
        "trend",
        "momentum_slow",
        ThesisType.MOMENTUM,
        dict(
            lookback=28,
            entry_threshold=0.20,
            exit_threshold=0.1,
            stop_loss_bps=200.0,
            take_profit_bps=340.0,
            cooldown_sec=720,
            size_usd=120.0,
            max_hold_sec=14400,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.05,
        ),
    ),
    (
        "trend",
        "momentum_wide",
        ThesisType.MOMENTUM,
        dict(
            lookback=20,
            entry_threshold=0.18,
            exit_threshold=0.09,
            stop_loss_bps=170.0,
            take_profit_bps=280.0,
            cooldown_sec=540,
            size_usd=110.0,
            max_hold_sec=10800,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.06,
        ),
    ),
    (
        "trend",
        "breakout",
        ThesisType.BREAKOUT,
        dict(
            lookback=24,
            entry_threshold=0.2,
            exit_threshold=0.3,
            stop_loss_bps=160.0,
            take_profit_bps=260.0,
            cooldown_sec=480,
            size_usd=110.0,
            max_hold_sec=7200,
            side_bias=SideBias.BOTH,
            breakout_buffer_bps=3.0,
            vol_filter_min=0.0,
            vol_filter_max=0.06,
        ),
    ),
    (
        "trend",
        "breakout_tight",
        ThesisType.BREAKOUT,
        dict(
            lookback=16,
            entry_threshold=0.18,
            exit_threshold=0.25,
            stop_loss_bps=130.0,
            take_profit_bps=210.0,
            cooldown_sec=360,
            size_usd=95.0,
            max_hold_sec=5400,
            side_bias=SideBias.BOTH,
            breakout_buffer_bps=2.5,
            vol_filter_min=0.0,
            vol_filter_max=0.06,
        ),
    ),
    (
        "trend",
        "breakout_wide",
        ThesisType.BREAKOUT,
        dict(
            lookback=32,
            entry_threshold=0.22,
            exit_threshold=0.35,
            stop_loss_bps=210.0,
            take_profit_bps=360.0,
            cooldown_sec=600,
            size_usd=115.0,
            max_hold_sec=14400,
            side_bias=SideBias.BOTH,
            breakout_buffer_bps=4.0,
            vol_filter_min=0.0,
            vol_filter_max=0.07,
        ),
    ),
    # --- contrarian island (7) ---
    (
        "contrarian",
        "mean_reversion",
        ThesisType.MEAN_REVERSION,
        dict(
            lookback=20,
            entry_threshold=0.85,
            exit_threshold=0.35,
            stop_loss_bps=110.0,
            take_profit_bps=160.0,
            cooldown_sec=420,
            size_usd=100.0,
            max_hold_sec=5400,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.04,
        ),
    ),
    (
        "contrarian",
        "mean_reversion_tight",
        ThesisType.MEAN_REVERSION,
        dict(
            lookback=12,
            entry_threshold=0.7,
            exit_threshold=0.25,
            stop_loss_bps=90.0,
            take_profit_bps=130.0,
            cooldown_sec=300,
            size_usd=85.0,
            max_hold_sec=3600,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.05,
        ),
    ),
    (
        "contrarian",
        "mean_reversion_wide",
        ThesisType.MEAN_REVERSION,
        dict(
            lookback=28,
            entry_threshold=1.0,
            exit_threshold=0.4,
            stop_loss_bps=130.0,
            take_profit_bps=190.0,
            cooldown_sec=480,
            size_usd=105.0,
            max_hold_sec=7200,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.045,
        ),
    ),
    (
        "contrarian",
        "mean_reversion_slow",
        ThesisType.MEAN_REVERSION,
        dict(
            lookback=24,
            entry_threshold=0.9,
            exit_threshold=0.3,
            stop_loss_bps=120.0,
            take_profit_bps=175.0,
            cooldown_sec=540,
            size_usd=110.0,
            max_hold_sec=9000,
            side_bias=SideBias.BOTH,
            vol_filter_min=0.0,
            vol_filter_max=0.04,
        ),
    ),
    (
        "contrarian",
        "fade",
        ThesisType.LIQUIDITY_FADE,
        dict(
            lookback=8,
            entry_threshold=0.3,
            exit_threshold=0.2,
            stop_loss_bps=100.0,
            take_profit_bps=150.0,
            cooldown_sec=300,
            size_usd=80.0,
            max_hold_sec=3600,
            side_bias=SideBias.BOTH,
            fade_move_bps=8.0,
            vol_filter_min=0.0,
            vol_filter_max=0.1,
        ),
    ),
    (
        "contrarian",
        "fade_tight",
        ThesisType.LIQUIDITY_FADE,
        dict(
            lookback=6,
            entry_threshold=0.25,
            exit_threshold=0.15,
            stop_loss_bps=85.0,
            take_profit_bps=125.0,
            cooldown_sec=240,
            size_usd=75.0,
            max_hold_sec=2700,
            side_bias=SideBias.BOTH,
            fade_move_bps=6.0,
            vol_filter_min=0.0,
            vol_filter_max=0.12,
        ),
    ),
    (
        "contrarian",
        "fade_slow",
        ThesisType.LIQUIDITY_FADE,
        dict(
            lookback=12,
            entry_threshold=0.3,
            exit_threshold=0.2,
            stop_loss_bps=115.0,
            take_profit_bps=170.0,
            cooldown_sec=360,
            size_usd=90.0,
            max_hold_sec=5400,
            side_bias=SideBias.BOTH,
            fade_move_bps=10.0,
            vol_filter_min=0.0,
            vol_filter_max=0.1,
        ),
    ),
]

assert len(BASELINE_TEMPLATES) == 14


def genome_from_template(overrides: dict[str, Any]) -> Genome:
    g = Genome()
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


def seed_from_baselines(
    n: int = 8,
    *,
    starting_cash: float = 2000.0,
) -> list[Organism]:
    """Build organisms from the first n baseline templates (1..14)."""
    n = max(1, min(14, int(n)))
    out: list[Organism] = []
    for island, label, thesis, overrides in BASELINE_TEMPLATES[:n]:
        out.append(
            Organism(
                id=new_id("org"),
                thesis_type=thesis,
                label=label,
                genome=genome_from_template(overrides),
                cash_usd=starting_cash,
            )
        )
    return out
