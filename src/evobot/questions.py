"""Versioned question library — every question declares a computable label (inv 5).

Labels name a factory that will score forecasts from the tape. Factories may be
stubbed today; the declaration is required before a question may enter the set.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

QUESTION_V = "core_v1"

# Choice criteria must be {label: description}; Score criteria are ordered arrays.
REGIME_CRITERIA = {
    "trending_up": "Price making higher highs / directional upside continuation",
    "trending_down": "Price making lower lows / directional downside continuation",
    "mean_reverting": "Oscillating around a local mean / stretched then fade",
    "chaotic": "No clear structure; high noise relative to signal",
    "other": "None of the above",
}

SETUP_CRITERIA = ["poor", "weak", "adequate", "strong", "excellent"]


def _label(
    *,
    name: str,
    kind: str,
    factory: str,
    horizon_bars: int,
    computable: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "factory": factory,
        "horizon_bars": int(horizon_bars),
        "computable": bool(computable),
        "notes": notes,
    }


# Small v1 set — questions that WILL get labels later.
QUESTION_SET: dict[str, dict[str, Any]] = {
    "regime": {
        "type": "choice",
        "instructions": (
            "Given only the named market buckets, which regime best describes "
            "the local tape over the next short horizon?"
        ),
        "criteria": REGIME_CRITERIA,
        "label": _label(
            name="forward_regime_15",
            kind="choice",
            factory="forward_trend_efficiency",
            horizon_bars=15,
            notes="Map realized trend efficiency + signed return into regime class.",
        ),
    },
    "toxic_flow": {
        "type": "noul",
        "instructions": (
            "Probability that the next move after this bar is adverse for a "
            "fresh taker entry (toxic / adverse selection), from buckets alone."
        ),
        "label": _label(
            name="adverse_move_noul",
            kind="noul",
            factory="triple_barrier_adverse",
            horizon_bars=10,
            notes="P(hit stop before TP) net of ~42 bps RT as ground truth.",
        ),
    },
    "setup_quality": {
        "type": "score",
        "instructions": (
            "Score setup quality for a generic short-horizon trade given only "
            "named buckets (poor…excellent)."
        ),
        "criteria": SETUP_CRITERIA,
        "label": _label(
            name="forward_setup_score",
            kind="score",
            factory="forward_edge_net_fees",
            horizon_bars=20,
            notes="Bucket realized net edge into poor…excellent rubric.",
        ),
    },
}


def questions_for_api(question_set: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Strip label metadata — Decisions API only wants type/instructions/criteria."""
    src = question_set or QUESTION_SET
    out: dict[str, Any] = {}
    for qid, q in src.items():
        entry: dict[str, Any] = {
            "type": q["type"],
            "instructions": q.get("instructions") or q.get("prompt") or "",
        }
        if "criteria" in q:
            entry["criteria"] = q["criteria"]
        out[qid] = entry
    return out


def every_question_declares_computable_label(
    question_set: Optional[dict[str, dict[str, Any]]] = None,
) -> list[str]:
    """Return list of qids that fail inv 5; empty means OK."""
    src = question_set or QUESTION_SET
    bad: list[str] = []
    for qid, q in src.items():
        lab = q.get("label")
        if not isinstance(lab, dict):
            bad.append(f"{qid}: missing label")
            continue
        if not lab.get("computable"):
            bad.append(f"{qid}: label.computable is not true")
        if not lab.get("factory"):
            bad.append(f"{qid}: label.factory missing")
        if not lab.get("name"):
            bad.append(f"{qid}: label.name missing")
        kind = lab.get("kind") or ""
        qtype = (q.get("type") or "").lower()
        if kind and qtype and kind != qtype and not (kind == "noul" and qtype == "noul"):
            # kind should match question type
            if kind != qtype:
                bad.append(f"{qid}: label.kind {kind!r} != type {qtype!r}")
    return bad


# --- Label factory stubs (declared; compute later from tape) -----------------

LabelFn = Callable[..., Any]

LABEL_FACTORIES: dict[str, LabelFn] = {}


def register_label_factory(name: str, fn: LabelFn) -> None:
    LABEL_FACTORIES[name] = fn


def _stub_forward_trend_efficiency(*_a: Any, **_k: Any) -> Optional[str]:
    """Stub — returns None until tape label factory lands."""
    return None


def _stub_triple_barrier_adverse(*_a: Any, **_k: Any) -> Optional[float]:
    return None


def _stub_forward_edge_net_fees(*_a: Any, **_k: Any) -> Optional[float]:
    return None


register_label_factory("forward_trend_efficiency", _stub_forward_trend_efficiency)
register_label_factory("triple_barrier_adverse", _stub_triple_barrier_adverse)
register_label_factory("forward_edge_net_fees", _stub_forward_edge_net_fees)


def resolve_label_factory(name: str) -> LabelFn:
    if name not in LABEL_FACTORIES:
        raise KeyError(f"unknown label factory {name!r}")
    return LABEL_FACTORIES[name]
