"""Repro F9: fitness charges LIFETIME turnover against PER-CADENCE PnL, so selection culls experience.

Run from the solana-evo-bot repo root:   python repro_F9_fitness_culls_experience.py
Uses the shipped rank_population(), select_retire_target(), PaperBroker and config.yaml. No network.

fitness.py:56   turnover = cadence_turnover if cadence_turnover is not None else organism.stats.turnover_usd
fitness.py:85   rank_population() never passes cadence_turnover  -> lifetime stats.turnover_usd is used
loop.py:743-751 the cadence reset zeroes realized_pnl_cadence / max_drawdown / alpha / beta, NOT turnover_usd

So every fill an organism has EVER made costs it  mu * notional  of fitness in EVERY later cadence, forever.
"""
import os

os.environ.setdefault("EVO_BOT_JEV_MOCK", "1")
from evo_bot.config import load_config
from evo_bot.evolution import select_retire_target
from evo_bot.fitness import rank_population
from evo_bot.models import Island, Organism, SignalAction, ThesisType
from evo_bot.paper_broker import PaperBroker
from evo_bot.risk import RiskManager

cfg = load_config("config.yaml")
cfg.risk.kill_switch_path = "/nonexistent/KILL"
broker = PaperBroker(RiskManager(cfg.risk), cfg.risk, cfg.fees)
KW = dict(symbol="SOL", mint="SOL", data_age_sec=0.0, open_trade_count=0)
mu = cfg.fitness.turnover_mu


def org(label):
    o = Organism(thesis_type=ThesisType.MEAN_REVERSION, island=Island.CONTRARIAN, label=label, cash_usd=2000.0)
    o.params.size_usd = 100.0
    return o


def round_trips(o, n, entry=100.0, exit_=101.5):
    for _ in range(n):
        broker.execute(o, SignalAction.BUY, mid=entry, **KW)
        broker.execute(o, SignalAction.SELL, mid=exit_, **KW)


try:                                        # patched repo: the loop's single reset function
    from evo_bot.fitness import reset_cadence_window as cadence_reset
    print("cadence reset : patched reset_cadence_window()")
except ImportError:                         # unpatched repo: exactly what loop.py:743-751 resets
    print("cadence reset : as shipped (loop.py:743-751)")

    def cadence_reset(o):
        o.realized_pnl_cadence = 0.0
        o.stats.fees_usd_cadence = 0.0
        o.stats.max_drawdown = 0.0
        o.stats.peak_equity = max(o.stats.peak_equity, o.cash_usd)


star = org("star: 4 winning round trips")
round_trips(star, 4)                        # +150 bps gross each, all winners
idle = [org(f"never traded #{i}") for i in range(1, 5)]
for o in idle:
    o.idle_cadences = 1                     # below idle_retire_cadences=2, so idle-retire does not rescue the star
print(f"turnover_mu={mu}   star lifetime: realized ${star.realized_pnl:+.2f}, fills={star.stats.n_trades}, "
      f"lifetime turnover ${star.stats.turnover_usd:,.0f}\n")

for title, act in (
    ("cadence N+1: star sits out (flat, no trades)", lambda: None),
    ("cadence N+2: star makes ANOTHER winning round trip (+150 bps gross)", lambda: round_trips(star, 1)),
):
    for o in [star] + idle:
        cadence_reset(o)
    act()
    ranked = rank_population([star] + idle, cfg.fitness)
    victim, score, why = select_retire_target(
        ranked, idle_retire_cadences=cfg.evolution.idle_retire_cadences,
        protect_min_realized_pnl=getattr(cfg.evolution, "protect_min_realized_pnl", 0.0))
    print(title)
    for o, s in ranked:
        print(f"   fitness {s:+8.2f}   cadence pnl {o.realized_pnl_cadence:+6.2f}   lifetime pnl {o.realized_pnl:+6.2f}   {o.label}")
    print(f"   -> RETIRED: '{victim.label}'  (reason={why})\n")

print("Unpatched: each $100 round trip adds $200 of turnover = $%.2f of penalty in EVERY future cadence.\n"
      "Patched  : the turnover term covers the current cadence only, so a sitting winner scores 0.00." % (mu * 200))
