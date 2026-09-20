"""Invariant 12: fitness terms share one window (F9)."""

from __future__ import annotations

from evobot.fitness import rank_population, reset_cadence_windows, window_fitness
from evobot.models import Organism, ThesisType, WindowStats


def test_fitness_depends_only_on_its_window():
    star = Organism(thesis_type=ThesisType.MOMENTUM, label="star", realized_pnl=500.0)
    star.window = WindowStats(n_trades=4, realized_pnl=0.0, turnover_usd=800.0)  # sitting this cadence
    idle = Organism(thesis_type=ThesisType.BREAKOUT, label="idle", realized_pnl=0.0)
    idle.window = WindowStats(n_trades=0, realized_pnl=0.0, turnover_usd=0.0)

    # Lifetime PnL / lifetime turnover must NOT drag star below idle
    assert window_fitness(star) == 0.0
    assert window_fitness(idle) == 0.0
    ranked = rank_population([star, idle])
    scores = {o.label: s for o, s in ranked}
    assert scores["star"] == scores["idle"] == 0.0

    # Winner this window beats loser regardless of lifetime
    winner = Organism(thesis_type=ThesisType.MOMENTUM, label="w", realized_pnl=-999.0)
    winner.window = WindowStats(n_trades=2, realized_pnl=12.0, turnover_usd=200.0)
    loser = Organism(thesis_type=ThesisType.MOMENTUM, label="l", realized_pnl=999.0)
    loser.window = WindowStats(n_trades=2, realized_pnl=-3.0, turnover_usd=200.0)
    ranked = rank_population([winner, loser])
    assert ranked[0][0].label == "w"
    assert ranked[0][1] == 12.0

    reset_cadence_windows([winner, loser])
    assert winner.window.realized_pnl == 0.0
    assert loser.window.n_trades == 0
