"""Crossover + declared mutation only. No post-spawn gene rewrite (inv 11 / F10).

Operators extracted from v1 evolution: crossover_params, MUTATION_NOISE,
ISLAND_NOISE_MULT, clamps, build_heritage, expiring-clamp tick/apply.
Dropped: bias_toward_firing, heritable exam genes, base-rate-blind graveyard mining.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from evobot.baselines import seed_from_baselines
from evobot.models import Genome, Organism, SideBias, ThesisType, new_id

# Declared mutation noise — strategy params only (no graduation/exam/Jev genes).
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

# Island / thesis-group mutation physics (Jev keys stripped — not in Genome).
ISLAND_NOISE_MULT: dict[str, dict[str, float]] = {
    "trend": {
        "max_hold_sec": 2.2,
        "breakout_buffer_bps": 2.0,
        "entry_threshold": 1.35,
        "take_profit_bps": 1.5,
        "ema_slow": 1.4,
    },
    "contrarian": {
        "entry_threshold": 0.45,
        "fade_move_bps": 0.55,
        "size_usd": 0.7,
        "stop_loss_bps": 0.65,
        "lookback": 0.6,
    },
}

TREND_THESES = frozenset({ThesisType.MOMENTUM, ThesisType.BREAKOUT, ThesisType.MICRO_TREND})
CONTRARIAN_THESES = frozenset({ThesisType.MEAN_REVERSION, ThesisType.LIQUIDITY_FADE})


def island_for_thesis(thesis: ThesisType) -> str:
    if thesis in TREND_THESES:
        return "trend"
    return "contrarian"


@dataclass
class EvolutionConfig:
    mutation_rate: float = 0.15
    continuous_avg_prob: float = 0.5
    idle_retire_cadences: int = 2
    starting_cash: float = 2000.0


def crossover_params(
    a: Genome,
    b: Genome,
    cfg: EvolutionConfig,
    rng: random.Random,
    *,
    weight_a: float = 0.5,
) -> Genome:
    """Evidence-weighted crossover of strategy genomes (alias of crossover_genomes)."""
    da, db = a.to_dict(), b.to_dict()
    wa = max(0.05, min(0.95, float(weight_a)))
    child: dict[str, Any] = {}
    for key, va in da.items():
        vb = db[key]
        if key in CONTINUOUS:
            if rng.random() < cfg.continuous_avg_prob:
                child[key] = wa * float(va) + (1.0 - wa) * float(vb)
            else:
                child[key] = float(va if rng.random() < wa else vb)
        else:
            child[key] = va if rng.random() < wa else vb
    return Genome.from_dict(child)


# Back-compat name used by earlier fable code / tests.
crossover_genomes = crossover_params


def clamp_genome_dict(data: dict[str, Any], *, thesis: Optional[ThesisType] = None) -> dict[str, Any]:
    """Sensible clamps — thesis-aware entry_threshold bands (F14 units)."""
    data["lookback"] = int(max(3, min(200, int(data["lookback"]))))
    data["ema_fast"] = int(max(2, min(50, int(data["ema_fast"]))))
    data["ema_slow"] = int(max(int(data["ema_fast"]) + 1, min(200, int(data["ema_slow"]))))
    data["size_usd"] = float(max(50.0, min(200.0, float(data["size_usd"]))))
    data["cooldown_sec"] = int(max(60, min(3600, int(data["cooldown_sec"]))))
    data["max_hold_sec"] = int(max(300, min(21600, int(data["max_hold_sec"]))))
    data["stop_loss_bps"] = float(max(40.0, min(500.0, float(data["stop_loss_bps"]))))
    data["take_profit_bps"] = float(max(50.0, min(800.0, float(data["take_profit_bps"]))))
    data["fade_move_bps"] = float(max(3.0, min(40.0, float(data["fade_move_bps"]))))
    data["breakout_buffer_bps"] = float(max(0.5, min(20.0, float(data["breakout_buffer_bps"]))))
    if data["vol_filter_max"] < data["vol_filter_min"]:
        data["vol_filter_min"], data["vol_filter_max"] = data["vol_filter_max"], data["vol_filter_min"]
    et = float(data["entry_threshold"])
    if thesis == ThesisType.MEAN_REVERSION:
        data["entry_threshold"] = max(0.3, min(3.0, et))
    elif thesis == ThesisType.MOMENTUM:
        data["entry_threshold"] = max(0.05, min(1.0, et))
    elif thesis == ThesisType.MICRO_TREND:
        data["entry_threshold"] = max(0.05, min(1.0, et))
    else:
        data["entry_threshold"] = max(0.05, min(3.0, et))
    return data


def mutate_genome(
    genome: Genome,
    cfg: EvolutionConfig,
    rng: random.Random,
    *,
    island: Optional[str] = None,
    thesis: Optional[ThesisType] = None,
    clamps: Optional[list[dict[str, Any]]] = None,
) -> Genome:
    data = genome.to_dict()
    mults = ISLAND_NOISE_MULT.get(island or "", {})
    for key, value in list(data.items()):
        if rng.random() > cfg.mutation_rate:
            continue
        noise = MUTATION_NOISE.get(key)
        if noise is None:
            if key == "side_bias":
                data[key] = rng.choice(list(SideBias)).value
            continue
        scale = float(mults.get(key, 1.0))
        n = noise * scale
        if key in CONTINUOUS:
            data[key] = max(0.0, float(value) + rng.uniform(-n, n))
        elif key in DISCRETE_INT:
            step = max(1, int(round(n)))
            data[key] = max(1, int(value) + rng.randint(-step, step))
    apply_mutation_clamps(data, clamps or [])
    return Genome.from_dict(clamp_genome_dict(data, thesis=thesis))


def tick_mutation_clamps(clamps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decrement remaining_cadences; drop expired (temporary, not permanent bans)."""
    out = []
    for c in clamps:
        rem = int(c.get("remaining_cadences", 0)) - 1
        if rem <= 0:
            continue
        nc = dict(c)
        nc["remaining_cadences"] = rem
        out.append(nc)
    return out


def apply_mutation_clamps(data: dict[str, Any], clamps: list[dict[str, Any]]) -> None:
    """In-place soft bounds after mutation. Strategy genes only (no exam/Jev)."""
    for c in clamps or []:
        gene = c.get("gene")
        if not gene or gene not in data:
            continue
        if "force_bool" in c:
            # Bool genes are not in fable Genome — ignore silently.
            continue
        if "min" in c:
            if gene in DISCRETE_INT:
                data[gene] = max(int(c["min"]), int(data[gene]))
            else:
                data[gene] = max(float(c["min"]), float(data[gene]))
        if "max" in c:
            if gene in DISCRETE_INT:
                data[gene] = min(int(c["max"]), int(data[gene]))
            else:
                data[gene] = min(float(c["max"]), float(data[gene]))


def build_heritage(parent_a: Organism, parent_b: Organism) -> dict[str, Any]:
    """Compact heritage card — strategy lineage only (no Jev/exam genes)."""

    def _card(o: Organism) -> dict[str, Any]:
        return {
            "id": o.id,
            "label": o.label,
            "thesis": o.thesis_type.value,
            "island": island_for_thesis(o.thesis_type),
            "generation": o.generation,
            "realized_pnl": float(o.realized_pnl),
            "window_pnl": float(o.window.realized_pnl),
            "n_trades": int(o.window.n_trades),
            "genome": o.genome.to_dict(),
        }

    return {"parents": [_card(parent_a), _card(parent_b)]}


def spawn_child(
    parent_a: Organism,
    parent_b: Organism,
    *,
    cfg: EvolutionConfig,
    rng: random.Random,
    thesis: Optional[ThesisType] = None,
    clamps: Optional[list[dict[str, Any]]] = None,
) -> Organism:
    """Inheritance + declared mutation ONLY. No fire_bias / post-spawn rewrite.

    Like-with-like (F14): prefer same thesis; if parents differ, pick one parent's
    thesis and take entry_threshold from that parent after crossover.
    """
    if thesis is not None:
        th = thesis
    elif parent_a.thesis_type == parent_b.thesis_type:
        th = parent_a.thesis_type
    else:
        # Cross-thesis: choose one parent as unit authority (no averaging units).
        th = parent_a.thesis_type if rng.random() < 0.5 else parent_b.thesis_type

    if parent_a.thesis_type == parent_b.thesis_type:
        genome = crossover_params(parent_a.genome, parent_b.genome, cfg, rng)
    else:
        # Prefer the genome whose thesis matches the child to avoid unit mix.
        donor = parent_a if parent_a.thesis_type == th else parent_b
        other = parent_b if donor is parent_a else parent_a
        genome = crossover_params(donor.genome, other.genome, cfg, rng, weight_a=0.75)
        # Force thesis-unit gene from donor
        genome.entry_threshold = donor.genome.entry_threshold

    island = island_for_thesis(th)
    genome = mutate_genome(genome, cfg, rng, island=island, thesis=th, clamps=clamps)
    heritage = build_heritage(parent_a, parent_b)
    child = Organism(
        id=new_id("org"),
        thesis_type=th,
        generation=max(parent_a.generation, parent_b.generation) + 1,
        label=f"gen{max(parent_a.generation, parent_b.generation) + 1}_{th.value[:3]}",
        genome=genome,
        cash_usd=cfg.starting_cash,
        parent_ids=(parent_a.id, parent_b.id),
    )
    # Stash heritage on a transient attribute for cadence logs (not a gene).
    setattr(child, "heritage", heritage)
    return child


def select_retire_target(
    ranked: Sequence[tuple[Organism, float]],
    *,
    idle_retire_cadences: int = 2,
) -> tuple[Organism, float, str]:
    """Idle-retire first; else worst fitness."""
    for org, score in ranked:
        if org.window.n_trades == 0 and org.idle_cadences + 1 >= idle_retire_cadences:
            return org, score, "idle"
    org, score = ranked[-1]
    return org, score, "worst_fitness"


def seed_colony(n: int = 8, *, starting_cash: float = 2000.0) -> list[Organism]:
    """Seed from mined v1 baseline templates (up to 14)."""
    return seed_from_baselines(n, starting_cash=starting_cash)
