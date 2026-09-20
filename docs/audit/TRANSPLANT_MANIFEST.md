# v1 → v2 transplant manifest (checked against the code)

Source: `solana-evo-bot-main.zip`, 23 modules, 9,904 LOC, 83 tests. Import graph built with `ast`, including lazy in-function imports. Companion: [`V1_AUDIT.md`](./V1_AUDIT.md).

## Correction to my earlier advice

From the README I told you to transplant `paper_broker` and `risk` "with their tests", and guessed 30–40% of the code would carry over. Having read the code:

- `paper_broker.execute()` is not a fill function. It mutates an `Organism` in place, stamps fills with the wall clock (F3) and calls risk internally. Only 38 lines of fee math are reusable.
- `risk.check_order()` vetoes closes (F2). Transplanting it would carry the bug.
- **About 17% of v1 survives** (≈1,700 of 9,904 LOC): 971 lines as-is, ≈390 extracted from the leaves, and after reviewing them, ≈200 from `evolution` and ≈150 from `dashboard`. That still strengthens the case for a new repo.
- No test file transplants whole. Even `test_fees.py` and `test_price_pool.py` import `population`, `fitness` or `backtest`. Individual test functions move; files do not.

## Why the leaves are not leaves

`models.py` is imported by 18 of 22 modules, and it is the old spine in data form. `GenomeParams` is one flat bag of ~50 fields mixing strategy parameters, 15 Jev policy genes, nursery graduation gates and Twitter genes. `Organism` carries cash, position, PnL, Jev α/β meters, lifecycle and heritage. Every module that takes an `Organism` or `GenomeParams` argument is coupled to the trunk through its signature even when its imports look clean. The rule for v2: nothing in `tape/`, `labels/`, `replay/` or `judge/` may accept an object that knows what an organism is.

## Manifest

| Module | LOC | Internal imports | Verdict | Take | Why |
|--------|-----|------------------|---------|------|-----|
| `price_pool` | 338 | none | **AS-IS** | all | Zero coupling. Add a `sources=` filter to `load_bars` (F6). |
| `price_backfill` | 289 | `price_pool` | **AS-IS** | all | Binance Vision + GeckoTerminal; CEX/DEX labeling is right. |
| `jev_client` | 344 | none | **AS-IS** | all | Allowlist asserted before HTTP, Decisions-only, mock path, billed `usage.cost`. Then add a content-addressed cache, async bulk mode, direct-API option. |
| `strategies` | 229 | `models` | **EXTRACT** | 91 lines: five `signal_*` fns, `_ema`, `_vol`, `_respect_side` | Pure functions of `(prices, params)`. Give each its own small params dataclass. `_stops`, `_in_cooldown`, `_max_hold_exit`, `generate_signal` are Organism-bound: rewrite as exit templates in `labels/` on an injected clock. |
| `paper_broker` | 252 | `config`, `models`, `risk` | **EXTRACT** | 38 lines: `round_trip_fee_drag_bps`, `passes_min_edge_gate`, `_fill_price`, `_fee_components` | The fee math is correct and is the lesson worth keeping. `execute()` is rewritten as a pure `fill(mid, side, notional, fees, now) -> Fill`; position state lives in a separate reducer. |
| `vol_fit` | 557 | `models`, `price_pool` | **EXTRACT** | ≈157 lines: `measure_tape`, `TapeMetrics`, `_percentile`, `_abs_ret_bps`, `_hl_range_bps`, `_atr_like_bps`, `_pstdev` | Tape percentiles are exactly what the named-bucket state encoders need. `score_vol_fit` (211) and `mutate_toward_vol_fit` (59) are genome nudging: delete. |
| `market_data` | 236 | `config`, `models`, `price_pool` | **EXTRACT** | ≈75 lines: `PriceHistory`, `_fetch_jupiter`, poll skeleton | Drop the synthetic fallback from the live path (F6) and the fabricated BTC/ETH walk (F5). On fetch failure v2 records a gap, never a made-up tick. |
| `models` | 303 | none | **EXTRACT** | 24 lines: `ThesisType`, `SignalAction`, `SideBias`, `PriceTick`, `WatchlistItem` | Everything else is the organism data model. |
| `jev_memory` | 67 | none | **REWRITE** | the append-only JSONL discipline | New schema keyed by `(symbol, bar, state_v, question_v, model_v)`. |
| `risk` | 85 | `config`, `models` | **REWRITE** | the limit list and the `data/KILL` file semantics | New rule: risk may block opens, never closes. Kill switch blocks opens and permits reduce-only. |
| `config` | 337 | `models` | **REWRITE** | `FeesConfig`, `RiskConfig` field names | Most of the 20 config classes describe deleted subsystems. |
| `persistence` | 64 | `config`, `models` | **REWRITE** | nothing | Trivial. |
| `jev_battery` | 483 | `models`, `paper_broker` | **REWRITE** | the question ids, as a to-do list for re-labeling | Becomes a versioned question library plus market-only state encoders. State today carries `ts`, `px`, ticker and mint address; criteria are bare degrees (F7). |
| `population` | 537 | `models` | **MINE** | the 14 seed parameter sets | They become the deterministic baseline templates and the triple-barrier exit templates. |
| `backtest` | 946 | 11 modules | **DELETE** | nothing | Closure of 11. Two clocks (F3), non-reproducible symbol choice (F8), gate logic entangled with replay. v2's replay core is new. |
| `jev_policy` | 402 | `jev_client`, `models` | **DELETE** | nothing | Hand thresholds on direct asks; gates exits (F1); sizes from Score magnitudes. Replaced by the combiner. |
| `fitness` | 90 | `config`, `models` | **DELETE** | nothing | Charges lifetime turnover against per-cadence PnL, so every trade permanently lowers fitness (F9). α/β reward agreeing with the judge under test. |
| `evolution` | 732 | 6 modules | **EXTRACT** | ≈200 lines: `crossover_params`, `MUTATION_NOISE` and `ISLAND_NOISE_MULT` tables, clamp ranges, `build_heritage`, the expiring-clamp idea | Reviewed after the first draft of this manifest (see `EVOLUTION_DASHBOARD_REVIEW.md`). The operators are sound and search-agnostic: they drive both policy search and the question colony. Drop `bias_toward_firing` (F10), the heritable exam genes (F12), base-rate-blind graveyard mining (F13) and cross-thesis gene mixing (F14). Orchestration is rewritten on replay. |
| `meta_critic` | 410 | `jev_client`, `jev_memory`, `models` | **DELETE** | nothing | Jev scoring parameter cards is a numeric, multi-hop, specialized-domain task: the three things the vendor says it is weak at. |
| `twitter_signal` | 508 | `config`, `models` | **DELETE** | nothing | Lexicon heuristic. Replaced by per-post Jev typing. |
| `loop` | 1382 | 18 modules | **DELETE** | nothing | The old spine. v2's `live/` is a thin tail of replay. |
| `dashboard` | 918 | 7 modules | **EXTRACT** | the single-file build, the dish visual language, `theory_bullets`/`theory_body`, `esc()` hygiene, `create_export_pack` | Rebuild GET-only over replay outputs (F11). Cells become questions; headline mark-to-market and paired Premium with its interval; invariant monitors above the fold (F15). Extend the pack with git SHA, config, nursery reports, ledger. |
| `cli` | 388 | 10 modules | **DELETE** | nothing | Follows the spine. |

**Test functions worth moving:** `test_allowlist_accepts_pin_and_latest`, `test_allowlist_rejects_other_models`, `test_mock_decide_deterministic_no_network` (from `test_jev.py`); the `round_trip_fee_drag_bps` and `passes_min_edge_gate` assertions in `test_fees.py`; the `PricePool` round-trip assertions in `test_price_pool.py`.

## Provenance

Record in v2's first commit: "Transplanted from coreycottrell/solana-evo-bot @ 89e18ba: price_pool, price_backfill, jev_client (as-is); extracts from strategies, paper_broker, vol_fit, market_data, models." Two days of history is not worth `git filter-repo`.

## Build order

1. `MISSION.md` (v2) and the invariant tests it names, before any feature code.
2. AS-IS modules plus their moved test functions, green.
3. `replay/` on an injected clock, with the property tests from MISSION §Invariants. No Jev.
4. `labels/`, then run the 14 baseline templates over years of Binance tape. This is the denominator: what clears ~42 bps round trip with no judgment layer.
5. `encoders/` and `judge/` store; backfill; baseline ladder and lift table.
6. Question colony, text lane, `live/` holdout, dashboard.
