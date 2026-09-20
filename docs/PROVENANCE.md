# Provenance

First commit of this repo (solana-evo-fable / v2 A/B arm):

Transplanted from `coreycottrell/solana-evo-bot` @ `322a88f2e3ad2c356d7590d3326be29470e7dda3`:

- AS-IS: `price_pool`, `price_backfill`, `jev_client` (imports → `evobot`; HTTP title → fable)
- Extract: fee math → `evobot.fees` (`round_trip_fee_drag_bps`, `passes_min_edge_gate`, `FeesConfig`)
- Small law-encoding edits on `price_pool`: reject `source=synthetic`; require injected `ts=`; `load_bars(..., sources=)` (F6)

Mission source: upload pack `MISSION_v2.md` → root `MISSION.md`.
Audit companions: `docs/audit/`.


## Transplant wave 2 (operators / dish / baselines)

From `coreycottrell/solana-evo-bot` @ `322a88f`:

- **EXTRACT** `strategies`: five `signal_*` + `_ema`/`_vol`/`_respect_side` as pure `(prices, params)` with thesis-scoped dataclasses (`MeanReversionParams`, `MomentumParams`, `BreakoutParams`, `LiquidityFadeParams`, `MicroTrendParams`); paper `generate_signal` projects `Genome` → thesis params.
- **EXTRACT** `vol_fit`: `measure_tape`, `TapeMetrics`, percentile/ATR helpers only — **not** `score_vol_fit` / `mutate_toward_vol_fit`.
- **EXTRACT** `evolution` operators: `crossover_params`, `MUTATION_NOISE`, `ISLAND_NOISE_MULT` (Jev keys stripped), clamps, `build_heritage`, expiring-clamp `tick`/`apply`. **Dropped** `bias_toward_firing`, heritable exam genes, base-rate-blind graveyard mining.
- **MINE** `population` → `baselines.BASELINE_TEMPLATES` (14 strategy-only seeds); `seed_colony` uses them.
- **fees**: `fee_components` + `fill_price`; `round_trip_fee_drag_bps` used on paper edge gate + snapshot.
- **dashboard**: dish UI + `theory_bullets`/`theory_body`/`esc`/`create_export_pack` (GET-only; SHA in pack).

**Not ported:** `backtest`, `jev_policy`, `fitness` (v1), `meta_critic`, `twitter_signal`, `loop`, risk-as-is (opens-only kept), heritable graduation genes.
