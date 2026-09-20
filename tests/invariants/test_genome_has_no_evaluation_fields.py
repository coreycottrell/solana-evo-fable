"""Invariant 11: the examiner is not heritable — no evaluation genes."""

from __future__ import annotations

import importlib.util

import pytest

# Fields that must never appear on a Genome / GenomeParams once it exists.
FORBIDDEN = frozenset(
    {
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
    }
)


def test_genome_has_no_evaluation_fields():
    """When Genome exists, it must not carry evaluation/graduation genes (F12)."""
    spec = importlib.util.find_spec("evobot.models")
    if spec is None:
        pytest.xfail("Genome/models not landed yet — invariant 11 stub (F12 heritable exam)")
    models = importlib.import_module("evobot.models")
    genome_cls = getattr(models, "Genome", None) or getattr(models, "GenomeParams", None)
    if genome_cls is None:
        pytest.xfail("Genome class not defined yet — invariant 11 stub")
    fields = set(getattr(genome_cls, "model_fields", {}) or {})
    if not fields and hasattr(genome_cls, "__annotations__"):
        fields = set(genome_cls.__annotations__)
    bad = fields & FORBIDDEN
    assert not bad, f"Genome carries evaluation fields (examiner heritable): {sorted(bad)}"
