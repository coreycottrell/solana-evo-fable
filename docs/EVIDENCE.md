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
| Dashboard is GET-only | BELIEVED → xfail | Dashboard not landed |

Discovery → validation → final test once. Anything that looks good gets a deflated-Sharpe check against the number of things tried (MISSION).
