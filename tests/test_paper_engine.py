"""Paper engine: steps, evolves on cadence, injected clock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from evobot.paper.engine import PaperEngine


def test_paper_evolves_on_cadence(tmp_path: Path):
    eng = PaperEngine(data_dir=tmp_path, n_organisms=6, cadence_sec=60.0, rng_seed=7)
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    # synthetic-looking mids for signal path are OK inside the test harness;
    # we do not write them to the price pool.
    prices = [100.0 + (i % 7) * 0.2 for i in range(80)]
    ids_before = {o.id for o in eng.state.organisms}

    for i in range(5):
        eng.step(t0 + timedelta(seconds=10 * i), prices, mid=prices[-1])

    # force cadence
    info = eng.step(t0 + timedelta(seconds=61), prices, mid=prices[-1])
    assert info["evolved"] is not None
    assert eng.state.n_evolves == 1
    ids_after = {o.id for o in eng.state.organisms}
    assert len(ids_after) == 6
    assert ids_after != ids_before  # one retired, one spawned
    assert eng.state.cadence_index == 1
