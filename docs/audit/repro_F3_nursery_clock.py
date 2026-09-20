"""Repro F3: nursery backtests mix two clocks, so every backtest is capped at one round trip.

Run from the solana-evo-bot repo root:   python repro_F3_nursery_clock.py

backtest.py drives signals with a SIMULATED clock:   now = datetime(2024, 1, 1) + bar_seconds * bar_i
paper_broker.py stamps fills with the WALL clock:    last_trade_at = opened_at = datetime.now(utc)
strategies.py compares them:
    _in_cooldown   : (now - last_trade_at) <  cooldown_sec   -> (2024 - 2026) is ~ -85,000,000 s -> ALWAYS True
    _max_hold_exit : (now - opened_at)     >= max_hold_sec   ->                                   -> NEVER True
After the first fill the organism is in cooldown for the rest of the backtest. Stops are checked before
cooldown, so the only possible exit is SL/TP, after which it never trades again.

Arm A = repo as shipped.  Arm B = identical, except the broker's datetime.now() returns the simulated bar
time that backtest.py already computes. Jev is OFF in both arms so the clock is the only difference.
"""
import atexit
import collections
import datetime as _dt
import logging
import os
import shutil
import tempfile

os.environ["EVO_BOT_JEV_MOCK"] = "1"
os.environ["EVO_BOT_FORCE_SYNTHETIC"] = "1"
logging.disable(logging.CRITICAL)

import evo_bot.backtest as bt
import evo_bot.paper_broker as pb
import evo_bot.strategies as st
from evo_bot.config import load_config
from evo_bot.population import seed_population

N_BARS, SEED = 900, 7                      # 900 = shipped nursery.bars (15 h of 1-min bars)
cfg = load_config("config.yaml")
cfg.price_pool.enabled = False
_scratch = tempfile.mkdtemp(prefix="evo_repro_")   # run_backtest caches ~1.4 MB of synthetic bars per seed;
cfg.nursery.bars_dir = cfg.paths.bars_dir = _scratch  # keep that out of the repo's data/bars
atexit.register(shutil.rmtree, _scratch, ignore_errors=True)             # deterministic synthetic bars
cfg.nursery.jev_mode = "off"
orgs = seed_population(starting_cash=2000.0, size=14)
for i, o in enumerate(orgs):
    o.params.bt_jev_mode = "off"
    o.id = f"org_{i:010d}"               # run_backtest picks the traded mint by hashing org.id, and ids are
                                           # random uuids, so without this the table changes on every run

reasons, SIM = collections.Counter(), {"now": None}
_orig = st.generate_signal


def spy(org, prices, price, symbol, mint, now=None):
    SIM["now"] = now
    sig = _orig(org, prices, price, symbol, mint, now=now)
    reasons[sig.reason.split("=")[0].split(" ")[0]] += 1
    return sig


bt.generate_signal = spy


class SimClock(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return SIM["now"] if SIM["now"] is not None else _dt.datetime.now(tz)


def run(arm):
    pb.datetime = SimClock if arm == "B" else _dt.datetime
    out = []
    for o in orgs:
        reasons.clear()
        rep = bt.run_backtest(o, cfg, n_bars=N_BARS, seed=SEED)
        out.append((o.label or o.thesis_type.value, rep.n_trades, reasons.get("cooldown", 0), rep.verdict))
    return out


A, B = run("A"), run("B")
print(f"{N_BARS} synthetic 1-min bars, seed={SEED}, Jev off, identical genomes\n")
print(f"{'organism':<22}| {'A fills':>7} {'A bars in cooldown':>19} {'A verdict':>12} | {'B fills':>7} {'B cooldown':>11} {'B verdict':>12}")
for a, b in zip(A, B):
    flip = "  <- verdict flips" if a[3] != b[3] else ""
    print(f"{a[0]:<22}| {a[1]:>7} {a[2]:>19} {a[3]:>12} | {b[1]:>7} {b[2]:>11} {b[3]:>12}{flip}")
tot = N_BARS * len(orgs)
print(f"\nA (repo clock) : every backtest has exactly {set(a[1] for a in A)} fills; "
      f"{sum(a[2] for a in A):,} of {tot:,} bars ({sum(a[2] for a in A) / tot:.1%}) returned 'cooldown'")
print(f"B (one clock) : fills range {min(b[1] for b in B)}-{max(b[1] for b in B)}; "
      f"{sum(b[2] for b in B):,} bars in cooldown; {sum(1 for a, b in zip(A, B) if a[3] != b[3])} graduation verdicts flip")
print("NOTE: on an unpatched repo arm B still contains F2 (close vetoes), so its fills/verdicts are not final;"
      " this script isolates the clock only.")
