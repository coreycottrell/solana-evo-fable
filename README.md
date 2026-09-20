# Solana Evo-Fable (v2 A/B arm)

**Mission:** see [`MISSION.md`](MISSION.md).

This repository is the **v2 / Fable** paper-only laboratory for A/B testing against the live **v1 colony** at `/workspace/solana-evo-bot` (GitHub: `coreycottrell/solana-evo-bot`).

| | v1 (live colony) | v2 / Fable (this repo) |
|--|------------------|-------------------------|
| Path | `/workspace/solana-evo-bot` | `/workspace/solana-evo-fable` |
| Role | Running paper colony | Rebuild under MISSION invariants |
| Data | `solana-evo-bot/data/` | `solana-evo-fable/data/` only (`EVO_BOT_V2_DATA_DIR`) |
| Dashboard (later) | `:8765` | `:8766` |
| Trading key | OpenRouter → **Jev only** | Same key, still **Jev only** |
| Scope | Full dual-island loop | Replay-first; AS-IS leaves first |

> **Safety:** Paper simulation only. No wallet signing. Hard risk never delegates exits to Jev (invariant 1). An invariant without a passing test is a wish.

## Status

- MISSION + invariant tests scaffolded (some xfail until models/dashboard/risk land).
- AS-IS transplants from v1 `@ 322a88f`: `price_pool`, `price_backfill`, `jev_client` (+ fee math leaf in `fees.py`).
- `load_bars(..., sources=...)` filter (F6). Synthetic ticks rejected on append (invariant 4).
- Wall clock banned outside `live/` (invariant 2); `append_tick` requires injected `ts=`.

Audit pack + v1 repro scripts: [`docs/audit/`](docs/audit/). Evidence tags: [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

## Setup

```bash
cd /workspace/solana-evo-fable
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Run v1 vs v2 side by side

**Do not stop v1.** Its paper loop and dashboard stay up.

```bash
# v1 (already running on the box — leave it alone)
#   python -m evo_bot --dashboard --dashboard-port 8765
#   python -m evo_bot --cadence 14400 --poll 90
#   data: /workspace/solana-evo-bot/data/

# v2 / Fable — separate venv, separate data dir, different port when dashboard lands
cd /workspace/solana-evo-fable
source .venv/bin/activate
export EVO_BOT_V2_DATA_DIR=/workspace/solana-evo-fable/data
export EVO_BOT_JEV_MOCK=1   # or share OPENROUTER_API_KEY (Jev allowlist still enforced)
pytest -q
# later: uvicorn / dashboard on :8766
```

Shared `OPENROUTER_API_KEY` is fine: both arms call allowlisted `typesafe/jev-*` Decisions only. Never point `EVO_BOT_V2_DATA_DIR` at v1's `data/`.

## Package

Python package: `evobot` under `src/evobot/`.
