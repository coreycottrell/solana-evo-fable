"""Data dir isolation — never write into v1."""

from __future__ import annotations

from pathlib import Path

import pytest

from evobot import paths


def test_default_data_dir_under_fable_repo():
    d = paths.data_dir()
    assert d.name == "data"
    assert "solana-evo-fable" in str(d)
    v1 = Path("/workspace/solana-evo-bot/data").resolve()
    assert d != v1
    assert not str(d).startswith(str(v1))


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "fable-data"
    monkeypatch.setenv("EVO_BOT_V2_DATA_DIR", str(target))
    d = paths.data_dir()
    assert d == target.resolve()
    assert d.is_dir()
