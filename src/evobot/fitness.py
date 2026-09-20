"""Fitness = cadence-window PnL only (inv 12). No lifetime turnover against window."""

from __future__ import annotations

from typing import Sequence

from evobot.models import Organism


def window_fitness(org: Organism) -> float:
    """Single-window score: realized PnL inside the current cadence window."""
    return float(org.window.realized_pnl)


def rank_population(orgs: Sequence[Organism]) -> list[tuple[Organism, float]]:
    scored = [(o, window_fitness(o)) for o in orgs]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def reset_cadence_windows(orgs: Sequence[Organism]) -> None:
    for o in orgs:
        o.reset_window()
