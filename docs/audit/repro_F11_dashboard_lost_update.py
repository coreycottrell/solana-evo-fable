"""Repro F11: dashboard write actions are silently reverted by the running loop.

Run from the solana-evo-bot repo root:   python repro_F11_dashboard_lost_update.py
No network (mock Jev, synthetic prices, scratch data dir).

loop.py:91   reads population.json ONCE at startup; afterwards it only writes it from memory (loop.py:367, every poll).
dashboard.py:746-818  POST /api/nursery/{id}/run|graduate|discard do load -> modify -> save on the SAME file
from a different process. No lock, no reload in the loop. The click "works", then the next poll overwrites it.
/discard also writes a graveyard file, so the graveyard records a death for an organism that is still trading,
and mine_graveyard_clamps() reads that file.
"""
import json
import logging
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

tmp = tempfile.mkdtemp(prefix="evo_dash_")
os.environ.update(EVO_BOT_JEV_MOCK="1", EVO_BOT_FORCE_SYNTHETIC="1")
logging.disable(logging.CRITICAL)

import yaml

# NOTE: EVO_BOT_DATA_DIR only moves paths.data_dir; population/trades/graveyard/ledger/price_pool stay under
# <repo>/data (config.py load_config + resolve_paths). So isolate with a scratch config instead.
raw = yaml.safe_load(open("config.yaml"))
raw.setdefault("paths", {}).update(
    data_dir=tmp, population_file=f"{tmp}/population.json", trades_file=f"{tmp}/trades.jsonl",
    cadences_file=f"{tmp}/cadences.jsonl", graveyard_dir=f"{tmp}/graveyard", nursery_dir=f"{tmp}/nursery",
    bars_dir=f"{tmp}/bars", jev_ledger=f"{tmp}/jev_ledger.jsonl", jev_memory_dir=f"{tmp}/jev_memory")
raw.setdefault("nursery", {}).update(report_dir=f"{tmp}/nursery", bars_dir=f"{tmp}/bars",
                                     jev_ledger=f"{tmp}/jev_ledger.jsonl", jev_memory_dir=f"{tmp}/jev_memory")
raw.setdefault("risk", {})["kill_switch_path"] = f"{tmp}/KILL"
raw.setdefault("price_pool", {})["dir"] = f"{tmp}/price_pool"
raw.setdefault("meta_critic", {}).update(enabled=False, population_file=f"{tmp}/meta_critics.json")
raw.setdefault("twitter", {})["enabled"] = False
cfg_path = os.path.join(tmp, "config.yaml")
yaml.safe_dump(raw, open(cfg_path, "w"))
os.environ["EVO_BOT_CONFIG"] = cfg_path                 # both "processes" below load this same config

from fastapi.testclient import TestClient

import evo_bot.loop as L
from evo_bot.config import load_config
from evo_bot.dashboard import create_app

L.console.quiet = True
cfg = load_config()
bot = L.EvoBot(cfg, rng_seed=3)                      # the "paper loop" process
bot.poll_and_trade()                                  # writes population.json
pop_path = cfg.paths.population_file


def on_disk():
    raw = json.load(open(pop_path))
    orgs = raw["organisms"] if isinstance(raw, dict) else raw
    return {o["id"]: o for o in orgs}


victim = bot.population.alive()[0].id
client = TestClient(create_app())                     # the "dashboard" process, same data dir
print(f"before click      : {len(on_disk())} organisms on disk; {victim[-8:]} present = {victim in on_disk()}")

r = client.post(f"/api/nursery/{victim}/discard")
print(f"click Discard     : HTTP {r.status_code} {r.json()}  -> on disk present = {victim in on_disk()}")
gdir = cfg.paths.graveyard_dir                       # graveyard ONLY (jev_memory/ also names files by org id)
grave = [f for f in (os.listdir(gdir) if os.path.isdir(gdir) else []) if victim in f]
print(f"graveyard file    : {grave}")

bot.poll_and_trade()                                  # the loop's next poll (<= 60 s later in production)
alive_in_loop = victim in {o.id for o in bot.population.alive()}
print(f"after next poll   : on disk present = {victim in on_disk()}; still alive and trading in the loop = {alive_in_loop}")
if r.status_code == 403 and not grave:
    print("RESULT            : FIXED. The dashboard refused the write; nothing on disk changed, no false death record.")
elif victim in on_disk() and alive_in_loop and grave:
    print("RESULT            : BUG. Dashboard action reverted by the loop; graveyard holds a death record for a living organism.")
else:
    print("RESULT            : inconclusive")
