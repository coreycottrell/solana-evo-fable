"""Live paper runner — ONLY place that reads the wall clock (inv 2)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evobot.paper.engine import PaperEngine
from evobot.paths import data_dir, price_pool_dir
from evobot.price_pool import PricePool

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_paper(
    *,
    cadence_sec: float = 14400.0,
    poll_sec: float = 90.0,
    n_organisms: int = 8,
    bar_lookback: int = 120,
    symbol: str = "SOL",
    dashboard_port: Optional[int] = None,
    once: bool = False,
) -> None:
    root = data_dir()
    pool = PricePool(price_pool_dir())
    engine = PaperEngine(
        data_dir=root,
        n_organisms=n_organisms,
        cadence_sec=cadence_sec,
    )
    log.info(
        "fable paper ON data=%s cadence=%ss poll=%ss orgs=%s ticks=%s",
        root,
        cadence_sec,
        poll_sec,
        len(engine.state.organisms),
        pool.tick_count(symbol),
    )

    dash_thread = None
    if dashboard_port:
        dash_thread = _start_dashboard(engine, dashboard_port)

    try:
        while True:
            now = _now()
            ticks = pool.load_ticks(symbol, limit=max(bar_lookback * 2, 300))
            mids = [float(t["mid"]) for t in ticks if t.get("mid")]
            mid = mids[-1] if mids else 0.0
            data_age = 0.0
            if ticks:
                last_ts = ticks[-1].get("ts")
                try:
                    from datetime import datetime as _dt

                    ts = _dt.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                    data_age = max(0.0, (now - ts).total_seconds())
                except Exception:  # noqa: BLE001
                    data_age = 0.0
            # If tape is stale and we have no live feed, still step on last mid
            # (paper lab). Append nothing fabricated.
            info = engine.step(now, mids, mid=mid, symbol=symbol, data_age_sec=data_age)
            if info.get("evolved"):
                log.info("EVOLVED %s", info["evolved"].get("child"))
            elif info["poll"] % 10 == 1:
                log.info(
                    "poll=%s mid=%.4f fills_tick=%s cadence=%s elapsed=%.0fs total_fills=%s",
                    info["poll"],
                    info["mid"],
                    info["fills"],
                    info["cadence_index"],
                    info["elapsed_sec"],
                    engine.state.n_fills,
                )
            if once:
                break
            time.sleep(max(1.0, poll_sec))
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        engine._save()
        if dash_thread is not None:
            pass  # daemon


def _start_dashboard(engine: PaperEngine, port: int) -> Any:
    import threading

    def _run() -> None:
        try:
            from evobot.dashboard import serve

            serve(engine, port=port)
        except Exception as exc:  # noqa: BLE001
            log.warning("dashboard failed: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="fable-dash")
    t.start()
    log.info("dashboard http://127.0.0.1:%s", port)
    return t
