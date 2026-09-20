"""Crossover + declared mutation only. No post-spawn gene rewrite (inv 11 / F10)."""

from __future__ import annotations

import random
from dataclasses import dataclass, fields
from typing import Any, Optional, Sequence

from evobot.models import Genome, Organism, SideBias, ThesisType, new_id

# Declared mutation noise — strategy params only (no graduation/exam genes).
MUTATION_NOISE: dict[str, float] = {
    "entry_threshold": 0.08,
    "exit_threshold": 0.05,
    "stop_loss_bps": 25.0,
    "take_profit_bps": 40.0,
    "size_usd": 12.0,
    "vol_filter_min": 0.0005,
    "vol_filter_max": 0.01,
    "breakout_buffer_bps": 2.5,
    "fade_move_bps": 5.0,
    "lookback": 5,
    "cooldown_sec": 120,
    "max_hold_sec": 1200,
    "ema_fast": 1,
    "ema_slow": 3,
}

CONTINUOUS = frozenset(
    {
        "entry_threshold",
        "exit_threshold",
        "stop_loss_bps",
        "take_profit_bps",
        "size_usd",
        "vol_filter_min",
        "vol_filter_max",
        "breakout_buffer_bps",
        "fade_move_bps",
    }
)
DISCRETE_INT = frozenset(
    {"lookback", "cooldown_sec", "max_hold_sec", "ema_fast", "ema_slow"}
)


@dataclass
class EvolutionConfig:
    mutation_rate: float = 0.15
    continuous_avg_prob: float = 0.5
    idle_retire_cadences: int = 2
    starting_cash: float = 2000.0


def crossover_genomes(a: Genome, b: Genome, cfg: EvolutionConfig, rng: random.Random) -> Genome:
    da, db = a.to_dict(), b.to_dict()
    child: dict[str, Any] = {}
    for key, va in da.items():
        vb = db[key]
        if key in CONTINUOUS:
            if rng.random() < cfg.continuous_avg_prob:
                child[key] = 0.5 * float(va) + 0.5 * float(vb)
            else:
                child[key] = float(va if rng.random() < 0.5 else vb)
        else:
            child[key] = va if rng.random() < 0.5 else vb
    return Genome.from_dict(child)


def mutate_genome(genome: Genome, cfg: EvolutionConfig, rng: random.Random) -> Genome:
    data = genome.to_dict()
    for key, value in list(data.items()):
        if rng.random() > cfg.mutation_rate:
            continue
        noise = MUTATION_NOISE.get(key)
        if key in CONTINUOUS and noise is not None:
            data[key] = max(0.0, float(value) + rng.uniform(-noise, noise))
        elif key in DISCRETE_INT and noise is not None:
            data[key] = max(1, int(value) + rng.randint(-int(noise), int(noise)))
        elif key == "side_bias":
            data[key] = rng.choice(list(SideBias)).value
    # sensible clamps
    data["lookback"] = int(max(3, min(200, int(data["lookback"]))))
    data["ema_fast"] = int(max(2, min(50, int(data["ema_fast"]))))
    data["ema_slow"] = int(max(int(data["ema_fast"]) + 1, min(200, int(data["ema_slow"]))))
    data["size_usd"] = float(max(50.0, min(200.0, float(data["size_usd"]))))
    data["cooldown_sec"] = int(max(60, min(3600, int(data["cooldown_sec"]))))
    data["max_hold_sec"] = int(max(300, min(21600, int(data["max_hold_sec"]))))
    data["entry_threshold"] = float(max(0.05, min(3.0, float(data["entry_threshold"]))))
    data["stop_loss_bps"] = float(max(40.0, min(500.0, float(data["stop_loss_bps"]))))
    data["take_profit_bps"] = float(max(50.0, min(800.0, float(data["take_profit_bps"]))))
    data["fade_move_bps"] = float(max(3.0, min(40.0, float(data["fade_move_bps"]))))
    data["breakout_buffer_bps"] = float(max(0.5, min(20.0, float(data["breakout_buffer_bps"]))))
    if data["vol_filter_max"] < data["vol_filter_min"]:
        data["vol_filter_min"], data["vol_filter_max"] = data["vol_filter_max"], data["vol_filter_min"]
    return Genome.from_dict(data)


def spawn_child(
    parent_a: Organism,
    parent_b: Organism,
    *,
    cfg: EvolutionConfig,
    rng: random.Random,
    thesis: Optional[ThesisType] = None,
) -> Organism:
    """Inheritance + declared mutation ONLY. No fire_bias / post-spawn rewrite."""
    genome = crossover_genomes(parent_a.genome, parent_b.genome, cfg, rng)
    genome = mutate_genome(genome, cfg, rng)
    th = thesis or parent_a.thesis_type
    # Prefer same thesis as fitter parent; allow rare flip within declared pool
    if rng.random() < 0.05:
        th = rng.choice(list(ThesisType))
    elif parent_a.thesis_type == parent_b.thesis_type:
        th = parent_a.thesis_type
    else:
        th = parent_a.thesis_type if rng.random() < 0.5 else parent_b.thesis_type
    return Organism(
        id=new_id("org"),
        thesis_type=th,
        generation=max(parent_a.generation, parent_b.generation) + 1,
        label=f"gen{max(parent_a.generation, parent_b.generation) + 1}_{th.value[:3]}",
        genome=genome,
        cash_usd=cfg.starting_cash,
        parent_ids=(parent_a.id, parent_b.id),
    )


def select_retire_target(
    ranked: Sequence[tuple[Organism, float]],
    *,
    idle_retire_cadences: int = 2,
) -> tuple[Organism, float, str]:
    """Idle-retire first; else worst fitness."""
    for org, score in ranked:
        if org.window.n_trades == 0 and org.idle_cadences + 1 >= idle_retire_cadences:
            return org, score, "idle"
    # worst is last after reverse sort
    org, score = ranked[-1]
    return org, score, "worst_fitness"


SEED_SPECS: list[tuple[ThesisType, str, dict[str, Any]]] = [
    (ThesisType.MOMENTUM, "mom_a", {"lookback": 12, "entry_threshold": 0.15, "size_usd": 100.0}),
    (ThesisType.MOMENTUM, "mom_b", {"lookback": 24, "entry_threshold": 0.25, "size_usd": 100.0}),
    (ThesisType.BREAKOUT, "bo_a", {"lookback": 20, "breakout_buffer_bps": 3.0, "size_usd": 100.0}),
    (ThesisType.BREAKOUT, "bo_b", {"lookback": 40, "breakout_buffer_bps": 6.0, "size_usd": 100.0}),
    (ThesisType.MEAN_REVERSION, "mr_a", {"lookback": 15, "entry_threshold": 1.2, "size_usd": 100.0}),
    (ThesisType.MEAN_REVERSION, "mr_b", {"lookback": 30, "entry_threshold": 1.8, "size_usd": 100.0}),
    (ThesisType.LIQUIDITY_FADE, "fade_a", {"lookback": 6, "fade_move_bps": 8.0, "size_usd": 100.0}),
    (ThesisType.LIQUIDITY_FADE, "fade_b", {"lookback": 8, "fade_move_bps": 14.0, "size_usd": 100.0}),
]


def seed_colony(n: int = 8, *, starting_cash: float = 2000.0) -> list[Organism]:
    n = max(4, min(8, n))
    out: list[Organism] = []
    for thesis, label, overrides in SEED_SPECS[:n]:
        g = Genome()
        for k, v in overrides.items():
            setattr(g, k, v)
        out.append(
            Organism(
                thesis_type=thesis,
                label=label,
                genome=g,
                cash_usd=starting_cash,
            )
        )
    return out
