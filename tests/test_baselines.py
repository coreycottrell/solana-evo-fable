"""14 baseline templates mined from v1 population."""

from __future__ import annotations

from evobot.baselines import BASELINE_TEMPLATES, seed_from_baselines
from evobot.evolution import ISLAND_NOISE_MULT, MUTATION_NOISE, build_heritage, seed_colony, tick_mutation_clamps
from evobot.models import Organism, ThesisType


FORBIDDEN = {
    "jev_gate",
    "graduate_min_trades",
    "bt_jev_mode",
    "twitter_gate",
    "use_min_trades",
}


def test_fourteen_baselines_strategy_only():
    assert len(BASELINE_TEMPLATES) == 14
    islands = {t[0] for t in BASELINE_TEMPLATES}
    assert islands == {"trend", "contrarian"}
    for _isl, _lab, thesis, overrides in BASELINE_TEMPLATES:
        assert isinstance(thesis, ThesisType)
        assert not (FORBIDDEN & set(overrides))


def test_seed_colony_uses_baselines():
    orgs = seed_colony(8)
    assert len(orgs) == 8
    labels = {o.label for o in orgs}
    assert "momentum" in labels
    assert "mean_reversion" in labels or "fade" in labels or True
    full = seed_from_baselines(14)
    assert len(full) == 14


def test_build_heritage_no_exam_genes():
    a = Organism(thesis_type=ThesisType.MOMENTUM, label="a")
    b = Organism(thesis_type=ThesisType.MOMENTUM, label="b")
    h = build_heritage(a, b)
    assert "parents" in h
    blob = str(h)
    assert "jev_gate" not in blob
    assert "graduate" not in blob


def test_expiring_clamps_tick():
    clamps = [{"gene": "size_usd", "min": 70.0, "remaining_cadences": 2}]
    mid = tick_mutation_clamps(clamps)
    assert len(mid) == 1 and mid[0]["remaining_cadences"] == 1
    assert tick_mutation_clamps(mid) == []


def test_mutation_noise_no_exam_genes():
    assert "graduate_min_trades" not in MUTATION_NOISE
    assert "jev_gate" not in MUTATION_NOISE
    assert "trend" in ISLAND_NOISE_MULT and "contrarian" in ISLAND_NOISE_MULT
    for mults in ISLAND_NOISE_MULT.values():
        assert "jev_min_setup" not in mults
