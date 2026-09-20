"""Invariant 2: no datetime.now / utcnow / time.time outside live/."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "evobot"
LIVE_ROOT = SRC_ROOT / "live"

# Call shapes the law bans (MISSION invariant 2).
BANNED_ATTRS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("time", "time"),
}


def _iter_py_files() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if p.is_file())


def _is_under_live(path: Path) -> bool:
    try:
        path.resolve().relative_to(LIVE_ROOT.resolve())
        return True
    except ValueError:
        return False


def _violations_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # datetime.now(...) / time.time(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            key = (func.value.id, func.attr)
            if key in BANNED_ATTRS:
                found.append(f"{path}:{node.lineno}: {func.value.id}.{func.attr}()")
        # utcnow() bare if imported that way — also catch Name utcnow
        if isinstance(func, ast.Name) and func.id == "utcnow":
            found.append(f"{path}:{node.lineno}: utcnow()")
    return found


def test_no_wall_clock_outside_live():
    """Greps the AST: wall clock banned outside live/."""
    violations: list[str] = []
    scanned = 0
    for path in _iter_py_files():
        if _is_under_live(path):
            continue
        scanned += 1
        violations.extend(_violations_in(path))
    assert scanned > 0, "expected to scan package modules"
    assert violations == [], "wall-clock calls outside live/:\n" + "\n".join(violations)
