# Provenance

First commit of this repo (solana-evo-fable / v2 A/B arm):

Transplanted from `coreycottrell/solana-evo-bot` @ `322a88f2e3ad2c356d7590d3326be29470e7dda3`:

- AS-IS: `price_pool`, `price_backfill`, `jev_client` (imports → `evobot`; HTTP title → fable)
- Extract: fee math → `evobot.fees` (`round_trip_fee_drag_bps`, `passes_min_edge_gate`, `FeesConfig`)
- Small law-encoding edits on `price_pool`: reject `source=synthetic`; require injected `ts=`; `load_bars(..., sources=)` (F6)

Mission source: upload pack `MISSION_v2.md` → root `MISSION.md`.
Audit companions: `docs/audit/`.
