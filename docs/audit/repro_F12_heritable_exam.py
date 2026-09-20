"""Repro F12: the examinee writes the exam. Graduation gates are heritable genes with no floor.

Run from the solana-evo-bot repo root:   python repro_F12_heritable_exam.py      (~1 min, no network)

backtest.py:66-108 resolve_effective_gates() clamps the numeric thresholds, but takes use_min_trades /
use_min_pnl / use_max_dd / use_hit_rate straight from the organism's own genes. evolution.py:471-478 flips
them by mutation. A child that disarms a gate passes more often, gets seated, and passes the disarmed gate on.

Paired design: the SAME 300 children are backtested twice; only use_min_pnl differs. Jev off, synthetic bars.
"""
import atexit
import collections
import logging
import os
import shutil
import tempfile
import random

os.environ.update(EVO_BOT_JEV_MOCK="1", EVO_BOT_FORCE_SYNTHETIC="1")
logging.disable(logging.CRITICAL)

import evo_bot.backtest as bt
from evo_bot.config import load_config
from evo_bot.evolution import spawn_child
from evo_bot.population import seed_population

cfg = load_config("config.yaml")
cfg.price_pool.enabled = False
_scratch = tempfile.mkdtemp(prefix="evo_repro_")   # run_backtest caches ~1.4 MB of synthetic bars per seed;
cfg.nursery.bars_dir = cfg.paths.bars_dir = _scratch  # keep that out of the repo's data/bars
atexit.register(shutil.rmtree, _scratch, ignore_errors=True)
cfg.nursery.jev_mode = "off"
seeds = seed_population(starting_cash=2000.0, size=14)
rng, res, n = random.Random(5), collections.Counter(), 0

for island in ("trend", "contrarian"):
    parents = [s for s in seeds if s.island.value == island]
    for _ in range(150):
        a, b = rng.sample(parents, 2)
        kid = spawn_child(a, b, starting_cash=2000.0, cfg=cfg.evolution, rng=rng, fire_bias=0.25)
        n += 1
        kid.id = f"org_{n:010d}"                       # pin id: run_backtest picks the mint by hashing it (F8)
        kid.params.bt_jev_mode, kid.params.use_min_trades, kid.params.use_max_dd = "off", False, True
        for armed in (True, False):
            kid.params.use_min_pnl = armed
            res[(armed, bt.run_backtest(kid, cfg, n_bars=900, seed=1000 + n).verdict)] += 1

for armed in (True, False):
    tot = sum(v for (a, _), v in res.items() if a == armed)
    print(f"min_pnl gate {'ARMED   ' if armed else 'DISARMED'}: pass {res[(armed, 'pass')]:>3}/{tot} = "
          f"{res[(armed, 'pass')] / tot:.0%}")
print("Same children, same tape. The only difference is a gene the child carries and its offspring inherit.")
