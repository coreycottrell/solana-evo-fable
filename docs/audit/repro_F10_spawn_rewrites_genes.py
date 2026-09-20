"""Repro F10: spawn_child() overwrites inherited genes before selection ever sees them.

Run from the solana-evo-bot repo root:   python repro_F10_spawn_rewrites_genes.py
Shipped spawn_child() + config.yaml. No network, no backtest, no price pool.

Both parents are identical: jev_gate=True, every graduation gate armed, entry_threshold=1.5.
A faithful GA would return children close to that. loop.py:497 sets fire_bias = 0.25 + 0.15*(attempt-1),
so bias_toward_firing() (evolution.py:549-573) runs on EVERY child, starting with the first attempt.
"""
import os
import random

os.environ.setdefault("EVO_BOT_JEV_MOCK", "1")
from evo_bot.config import load_config
from evo_bot.evolution import spawn_child
from evo_bot.models import Island, Organism, ThesisType

cfg = load_config("config.yaml")
N = 4000


def parent():
    o = Organism(thesis_type=ThesisType.MEAN_REVERSION, island=Island.CONTRARIAN, cash_usd=2000.0)
    p = o.params
    p.jev_gate, p.use_min_trades, p.use_min_pnl, p.use_max_dd = True, True, True, True
    p.entry_threshold, p.bt_jev_mode = 1.5, "live_sparse"
    return o


a, b = parent(), parent()
print(f"parents: jev_gate=True, use_min_trades=True, use_min_pnl=True, use_max_dd=True, entry_threshold=1.50, "
      f"bt_jev_mode=live_sparse   (mutation_rate={cfg.evolution.mutation_rate})\n")
print(f"{'nursery attempt':<16}{'fire_bias':>10} | {'jev_gate OFF':>13}{'min_trades gate OFF':>21}{'min_pnl gate OFF':>18}"
      f"{'max_dd gate OFF':>17}{'BT Jev off/mock':>17}{'mean entry_thr':>16}")
for attempt in (1, 2, 3, 4, 5, 6):
    fb = min(1.5, 0.25 + 0.15 * (attempt - 1))          # loop.py:497
    rng = random.Random(attempt)
    kids = [spawn_child(a, b, starting_cash=2000.0, cfg=cfg.evolution, rng=rng, fire_bias=fb).params for _ in range(N)]
    share = lambda f: sum(1 for k in kids if f(k)) / N
    print(f"{attempt:<16}{fb:>10.2f} | {share(lambda k: not k.jev_gate):>12.0%} {share(lambda k: not k.use_min_trades):>20.0%} "
          f"{share(lambda k: not k.use_min_pnl):>17.0%} {share(lambda k: not k.use_max_dd):>16.0%} "
          f"{share(lambda k: k.bt_jev_mode != 'live_sparse'):>16.0%} {sum(k.entry_threshold for k in kids) / N:>15.2f}")
print("\nmin_pnl / max_dd only flip by mutation (~7.5% per generation); the rest is bias_toward_firing().")
