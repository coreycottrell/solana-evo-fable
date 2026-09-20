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

- MISSION + invariant tests (market-only state, question labels, both-arms logging).
- AS-IS transplants from v1 `@ 322a88f`: `price_pool`, `price_backfill`, `jev_client` (+ fee math leaf in `fees.py`).
- **v2 Jev (log-only):** market-bucket state encoder, versioned `core_v1` questions with declared labels,
  judgment store under `data/judgments/`, paper poll calls on signal/sparse, both arms logged.
  Exits never gated by Jev. Dashboard `:8766` shows last Jev / call count / cost.
- `OPENROUTER_API_KEY` via symlink to v1 `.env` (gitignored). Mock off when key present.
- Wall clock banned outside `live/` (invariant 2).

```bash
python -m evobot --jev-once          # one live Decisions call
python -m evobot --paper --dashboard --port 8766
```

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
# EVO_BOT_JEV_MOCK defaults off when OPENROUTER_API_KEY is resolvable (symlink .env from v1)
pytest -q
# later: uvicorn / dashboard on :8766
```

Shared `OPENROUTER_API_KEY` is fine: both arms call allowlisted `typesafe/jev-*` Decisions only. Never point `EVO_BOT_V2_DATA_DIR` at v1's `data/`.

## Package

Python package: `evobot` under `src/evobot/`.
