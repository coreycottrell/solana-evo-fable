"""Invariant 11: spawn = crossover + declared mutation only (F10/F12)."""

from __future__ import annotations

import random
from dataclasses import fields

from evobot.evolution import MUTATION_NOISE, EvolutionConfig, spawn_child
from evobot.models import Genome, Organism, ThesisType

FORBIDDEN = {
    "nursery_min_trades",
    "nursery_min_net_pnl",
    "nursery_max_drawdown",
    "graduate_min_trades",
    "graduate_min_net_pnl_usd",
    "graduate_max_drawdown_usd",
    "jev_call_budget",
    "jev_max_calls",
    "judge_mode",
    "exam_mode",
    "bt_jev_mode",
    "force_graduate_after",
    "jev_gate",
    "use_min_trades",
    "use_min_pnl",
    "use_max_dd",
}


def test_genome_fields_are_strategy_only():
    names = {f.name for f in fields(Genome)}
    assert not (names & FORBIDDEN)
    # mutation table only covers genome fields
    assert set(MUTATION_NOISE) <= names


def test_spawn_is_inheritance_plus_declared_mutation():
    cfg = EvolutionConfig(mutation_rate=0.0)  # deterministic inheritance path
    a = Organism(
        thesis_type=ThesisType.MEAN_REVERSION,
        label="a",
        genome=Genome(entry_threshold=1.5, lookback=20, fade_move_bps=12.0),
    )
    b = Organism(
        thesis_type=ThesisType.MEAN_REVERSION,
        label="b",
        genome=Genome(entry_threshold=1.5, lookback=20, fade_move_bps=12.0),
    )
    rng = random.Random(0)
    child = spawn_child(a, b, cfg=cfg, rng=rng)
    # With mutation_rate=0 and identical parents, child genes == parents (no fire_bias rewrite)
    assert child.genome.entry_threshold == 1.5
    assert child.genome.lookback == 20
    assert child.genome.fade_move_bps == 12.0
    assert child.generation == 1
    assert set(child.parent_ids) == {a.id, b.id}
    # no evaluation fields sneaked onto child
    child_keys = set(child.genome.to_dict())
    assert not (child_keys & FORBIDDEN)
