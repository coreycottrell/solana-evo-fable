# Mission (v2)

**Evo-Bot v2** is a paper-only laboratory for one question: *which cheap, typed judgments about market state and market text carry information that survives fees, out of sample?* Jev makes judgment nearly free. v2 spends that on breadth and on a stream of scoreable forecasts, and lets evidence decide what the judgments are worth.

It is not a get-rich bot, a chat agent that picks coins, or a live wallet. v1 proved the plumbing works. It also proved that invariants written in prose are not invariants: v1's docs said "hard risk is never delegated to Jev" while its code let a Jev rule block a stop-loss, with 83 tests green. In v2 every invariant below names the test that enforces it. **An invariant without a passing test is a wish.**

---

## Invariants (the law)

1. **Exits are never gated.** No judgment layer, risk limit or kill switch may block an order that reduces a position. Risk blocks opens only.
   *Test:* `test_any_position_can_always_close` (any size, any price, kill switch on, every Jev answer adversarial).
2. **One clock, injected.** No `datetime.now()`, `utcnow()` or `time.time()` outside `live/`. Everything else receives `now`.
   *Tests:* `test_no_wall_clock_outside_live` (greps the tree); `test_replay_invariant_to_system_clock`.
3. **Replay-first.** Every number the system acts on is reproducible from `(tape, judgment store, config)` by replay. `live/` is a thin tail of the same replay code path. Same inputs, same outputs, bit for bit.
   *Test:* `test_replay_is_deterministic`; `test_live_step_equals_replay_step`.
4. **Real tape only.** Synthetic data exists in tests and nowhere else. A failed fetch records a gap, never a made-up tick. No input to a judgment may be fabricated.
   *Test:* `test_pool_rejects_synthetic_source`; `test_state_fields_have_real_provenance`.
5. **No question without a label.** A question enters the library only if it names a label that code computes from the tape (triple-barrier outcome net of fees, forward trend efficiency, forward vol, and so on). If ground truth cannot be computed, the question is unfalsifiable and stays out.
   *Test:* `test_every_question_declares_a_computable_label`.
6. **Jev is a feature until it earns more.** Jev answers are columns. A learned combiner consumes them. Jev is credited only with out-of-sample lift over the numeric-only baseline, on purged chronological splits, with a paired confidence interval. No hand-set thresholds on direct asks; no sizing from Score magnitudes.
   *Test:* `test_lift_report_has_baseline_and_ci`.
7. **Market-only state.** Jev state contains no organism, thesis, side or inventory, so one call serves every consumer. Backfill state contains no timestamps, absolute prices, tickers or addresses. Numbers arrive as code-computed named buckets.
   *Test:* `test_backfill_state_has_no_identifiers`.
8. **The live book is the holdout.** Live runs frozen champions only. Every signal logs both arms (with-Jev action and without-Jev action) so Premium is a paired statistic with an interval. Nothing is tuned on live results.
   *Test:* `test_live_logs_both_arms`.
9. **Tests assert outcomes, not execution.** "It fires in the log" is not evidence. Replay has property tests: a zero-threshold, zero-cooldown strategy trades on every eligible bar; trade count scales with bar count; fees on a round trip equal the closed-form number.
10. **Paper only. Jev-only on the trading key.** Pinned model version, logged per response. Proposer LLMs run offline on a separate key and never touch the trading path.
11. **The examiner is not heritable.** No gene may change how its carrier is evaluated: no graduation gates, judge modes or call budgets in the genome. Nothing edits a child's genes between inheritance and evaluation; any prior lives in the declared mutation distribution.
   *Tests:* `test_genome_has_no_evaluation_fields`; `test_spawn_is_inheritance_plus_declared_mutation`.
12. **Fitness terms share one window.** Fitness for window W depends only on events inside W. No lifetime stock is charged against a per-window flow.
   *Test:* `test_fitness_depends_only_on_its_window`.
13. **Inference about the dead compares against the living.** Any rule mined from failures uses an enrichment ratio with an interval, and can push in both directions.
   *Test:* `test_graveyard_rule_is_two_sided_and_base_rated`.
14. **Observers only observe.** The dashboard exposes GET routes only and opens data read-only. One process owns each state file.
   *Test:* `test_dashboard_has_no_mutating_routes`.

## Evidence standard

Every claim in a report is tagged **MEASURED** (with the script that reproduces it) or **BELIEVED**. A status of "working" requires a MEASURED outcome, not a log line.

Discovery uses the dev period. Model selection uses a validation period. The final test period is scored once. Anything that looks good gets a deflated-Sharpe check against the number of things tried.

---

## What we are building

1. **A label factory.** For every symbol and bar, code computes what would have happened to each baseline template, per side and horizon, net of the ~42 bps round trip.
2. **A judgment store.** Versioned questions × market-only state, keyed by `(symbol, bar, state_v, question_v, model_v)`, backfilled once and reused by everything.
3. **A boring combiner.** Logistic or gradient-boosted, walk-forward, recalibrated. Numeric-only baseline first.
4. **A question colony.** The genome is a question. Fitness is out-of-sample incremental information. Offline proposers write mutations; Jev measures them across the whole tape; code scores them. The graveyard records hypotheses that carried no information.
5. **A text lane.** Jev reads raw posts and events and emits typed records (which token, event type, new or rehash, promo or bot, credibility, stance). Code aggregates; event studies say which types move price over which horizon. Universe of 50–200 symbols.
6. **A holdout.** The live paper book, as defined in invariant 8.

## North-star outcome

- A lift table, reproducible by one command, that states with an interval what each Jev feature family adds over the numeric baseline. Zero is an acceptable answer.
- At least one champion policy whose live paired Premium interval excludes zero over a multi-week window.
- A stranger can read this file, run the test suite and one replay, and see why the colony believes what it believes.

## Explicitly not the mission

- Gating trades on a judgment that has not shown lift
- Asking Jev about data that is not in the state
- Evolving anything on live, wall-clock PnL
- Declaring anything "working" because it executes
- Live wallet signing, in this repo, ever

## Lessons carried from v1

| v1 finding | v2 invariant |
|------------|--------------|
| A Jev rule blocked a stop-loss; a notional cap blocked closes | 1 |
| Backtests ran on two clocks and could make one round trip each | 2, 3, 9 |
| Synthetic ticks entered the pool; BTC/ETH "macro" inputs were an RNG | 4 |
| Questions asked about order flow that was not in the state | 5 |
| The highest-rated setups were silently vetoed, censoring the comparison | 6, 8 |
| Per-organism state meant 6,000 answers nobody could reuse | 7 |
| Lifetime turnover was charged against cadence PnL, so every trade lowered fitness and the winner was culled | 12 |
| Spawn rewrote genes and the exam was heritable, so the nursery bred for exam evasion | 11 |
| Graveyard clamps ignored base rates and could only push toward more Jev | 13 |
| Dashboard clicks were reverted by the loop and left death records for living organisms | 14 |
| 83 green tests caught none of it | 9 |

## How to use this file

Before adding a feature, ask: **which invariant does it touch, and which test proves it still holds?** If the answer is "none, it just makes the demo louder", it does not belong on the critical path. If a change needs an invariant relaxed, change this file and its test first, in their own commit, with the reason.
