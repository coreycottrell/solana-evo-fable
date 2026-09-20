"""Data-directory isolation for the v2 / fable A/B arm.

Default: ``<repo>/data/``. Override with ``EVO_BOT_V2_DATA_DIR`` (or
``EVO_FABLE_DATA_DIR``). Never write into v1's ``solana-evo-bot/data/``.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA = _REPO_ROOT / "data"


def data_dir() -> Path:
    raw = (
        os.environ.get("EVO_BOT_V2_DATA_DIR")
        or os.environ.get("EVO_FABLE_DATA_DIR")
        or ""
    ).strip()
    root = Path(raw).expanduser() if raw else _DEFAULT_DATA
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def price_pool_dir() -> Path:
    d = data_dir() / "price_pool"
    d.mkdir(parents=True, exist_ok=True)
    return d
