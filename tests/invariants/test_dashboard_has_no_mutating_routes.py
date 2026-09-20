"""Invariant 14: observers only observe — GET routes only."""

from __future__ import annotations

import importlib.util

import pytest

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def test_dashboard_has_no_mutating_routes():
    """Dashboard (when present) must expose GET-only routes (F11)."""
    spec = importlib.util.find_spec("evobot.dashboard")
    if spec is None:
        pytest.xfail("dashboard not landed yet — invariant 14 stub (F11 lost update)")
    dash = importlib.import_module("evobot.dashboard")
    app = getattr(dash, "app", None)
    if app is None:
        pytest.xfail("dashboard.app not defined yet")
    routes = getattr(app, "routes", [])
    bad = []
    for route in routes:
        methods = set(getattr(route, "methods", None) or [])
        mut = methods & MUTATING
        if mut:
            bad.append(f"{getattr(route, 'path', route)} -> {sorted(mut)}")
    assert not bad, "mutating dashboard routes:\n" + "\n".join(bad)
