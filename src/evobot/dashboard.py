"""GET-only observer dashboard (inv 14)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_snapshot_fn: Optional[Callable[[], dict[str, Any]]] = None

try:
    from fastapi import FastAPI

    app = FastAPI(title="evo-fable", docs_url=None, redoc_url=None)

    @app.get("/")
    def root() -> dict[str, Any]:
        if _snapshot_fn is None:
            return {"name": "solana-evo-fable", "status": "idle"}
        snap = _snapshot_fn()
        return {
            "name": "solana-evo-fable",
            "status": "paper",
            "cadence_index": snap["cadence_index"],
            "n_evolves": snap["n_evolves"],
            "n_fills": snap["n_fills"],
            "poll_count": snap["poll_count"],
            "generation_max": snap["generation_max"],
            "organisms": snap["organisms"],
            "last_evolve": snap["last_evolve"],
            "last_step_at": snap["last_step_at"],
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/snapshot")
    def snapshot() -> dict[str, Any]:
        if _snapshot_fn is None:
            return {}
        return _snapshot_fn()

except ImportError:  # pragma: no cover
    app = None  # type: ignore[assignment]


def serve(engine: Any, *, port: int = 8766, host: str = "127.0.0.1") -> None:
    global _snapshot_fn
    if app is None:
        raise RuntimeError("pip install 'solana-evo-fable[dashboard]'")
    import uvicorn

    _snapshot_fn = engine.snapshot
    uvicorn.run(app, host=host, port=port, log_level="warning")
