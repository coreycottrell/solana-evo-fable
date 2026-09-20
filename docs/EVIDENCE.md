# Evidence standard (MEASURED vs BELIEVED)

Every claim in a report is tagged:

| Tag | Meaning |
|-----|---------|
| **MEASURED** | Reproducible by a named script or pytest; same inputs → same outputs. |
| **BELIEVED** | Hypothesis, design intent, or anecdote. Not yet scored. |

A status of "working" requires a **MEASURED** outcome, not a log line.

## Current ledger

| Claim | Tag | How to reproduce |
|-------|-----|------------------|
| v1 paper colony runs on `:8765` with 4h cadence | BELIEVED (ops) | Observe host processes; not owned by this repo |
| Invariant tests encode MISSION law | MEASURED | `pytest tests/invariants` |
| `PricePool` rejects `source=synthetic` | MEASURED | `test_pool_rejects_synthetic_source` |
| No wall clock outside `live/` in this tree | MEASURED | `test_no_wall_clock_outside_live` |
| Jev allowlist rejects non-Jev models before HTTP | MEASURED | `test_allowlist_*` |
| Fee drag rule-of-thumb (~26 bps on $100) | MEASURED | `test_round_trip_fee_drag_bps_rule_of_thumb` |
| Any position can always close (F1) | BELIEVED → xfail | Risk rewrite not landed; see `test_any_position_can_always_close` |
| Genome has no evaluation fields | BELIEVED → xfail | Genome model not landed |
| Dashboard is GET-only | MEASURED | `test_dashboard_has_no_mutating_routes` |
| Backfill state has no identifiers | MEASURED | `test_backfill_state_has_no_identifiers` |
| Every question declares computable label | MEASURED | `test_every_question_declares_a_computable_label` |
| Paper logs both Jev arms | MEASURED | `test_live_logs_both_arms` |
| Live Jev Decisions returns real model id | MEASURED | `python -m evobot --jev-once` → `typesafe/jev-1.13-20260917` in `data/jev_ledger.jsonl` |

Discovery → validation → final test once. Anything that looks good gets a deflated-Sharpe check against the number of things tried (MISSION).
