# Review: `evolution.py` and `dashboard.py`

Continues [`V1_AUDIT.md`](./V1_AUDIT.md) (F1–F8). Same source, same method, same evidence tags: **MEASURED** = a script in this pack reproduces it against unmodified code; **READ** = verified at the cited lines. `fitness.py` is included because it is the objective evolution optimizes.

## Verdict

These are the two most portable ideas in the repo. A search engine and a window onto it do not care what is being searched, so both survive the move to v2 while most of the trunk does not.

As built, though, evolution selects for the opposite of what you want, for four measured reasons that have nothing to do with sample size. And the dashboard is well made, but it is not read-only, it headlines the numbers that are broken, and it cannot show the failures that matter.

| # | Severity | Finding | Tag |
|---|----------|---------|-----|
| F9 | Critical | Fitness charges lifetime turnover against per-cadence PnL: every trade permanently lowers fitness | MEASURED |
| F10 | Critical | `spawn_child` overwrites inherited genes before selection sees them | MEASURED |
| F11 | High | Dashboard write actions are silently reverted by the loop, and leave false death records | MEASURED |
| F12 | High | The examinee writes the exam: graduation gates are heritable and the nursery selects for disarming them | MEASURED |
| F13 | High | Graveyard clamps ignore base rates and can only push toward more Jev | READ |
| F14 | Medium | One gene, several units: `entry_threshold` means different things per thesis and is crossed anyway | READ |
| F15 | Medium | Dashboard headlines broken metrics and has no mark-to-market | READ |
| F16 | Medium | `EVO_BOT_DATA_DIR` does not relocate state | READ |

---

## Evolution

### What is good

- The population invariant (worst stays seated until a child graduates) is careful engineering.
- Island isolation with per-island mutation physics (`ISLAND_NOISE_MULT`) is a sound way to keep two search regimes alive.
- Clamps keep genes sane (`ema_slow > ema_fast`, tape-derived threshold bands) and graveyard clamps expire instead of banning forever.
- Heritage cards and the graveyard are the right instinct: lineage and death are recorded, not overwritten.
- The loop passes one seeded `random.Random` through every operator, so the operators themselves are reproducible.

### F9 — Every trade permanently lowers fitness (MEASURED)

`fitness.py:56` uses `organism.stats.turnover_usd` whenever `cadence_turnover` is not supplied. `rank_population` (`fitness.py:85`) never supplies it, and nothing else in `src/` or `tests/` does either. The cadence reset (`loop.py:743-751`) zeroes cadence PnL, drawdown, α and β, but not turnover. So a **per-cadence flow** (PnL) is compared against a **lifetime stock** (turnover) that only grows. Drawdown has the same shape in effect: `max_drawdown` resets but `peak_equity` is an all-time high, so an organism below its ATH re-registers that drawdown every cadence.

`repro_F9_fitness_culls_experience.py`, shipped config (μ = 0.01):
```
star: 4 winning round trips, lifetime +$4.31, turnover $805 -> standing penalty $8.05 per cadence
cadence N+1 (star sits out)            fitness -8.05  vs four never-traders at 0.00  -> star RETIRED
cadence N+2 (star wins AGAIN, +$1.08)  fitness -8.99                                 -> star RETIRED
```
Each $100 round trip costs $2.00 of fitness in every later cadence, forever. A winning trade makes the winner's fitness worse. The optimal policy under this objective is to never trade.

Consequences: this, more than quiet tape, is why the colony filled with idle parkers (fix #6 patched the symptom). The +$34 leader survives only while a never-trader is available for idle-retire; `protect_min_realized_pnl` guards the idle path only, not `worst_fitness`. And **Jev Premium** (`loop.py:1025-1060`) is a difference of mean fitness between gated and ungated cohorts, so it mechanically favors whichever cohort has traded less. Gated organisms are blocked more, so they trade less.

**Patch:** pass cadence turnover, or reset `turnover_usd` with the other cadence fields. Better: every fitness term computed over the same window.

### F10 — Spawn overwrites inheritance (MEASURED)

`loop.py:497` sets `fire_bias = 0.25 + 0.15·(attempt−1)`, so `bias_toward_firing` (`evolution.py:549-573`) runs on **every** child, including first attempts. It runs after crossover, mutation and graveyard clamps, so it wins. `repro_F10_spawn_rewrites_genes.py`, two identical fully-gated parents, 4,000 children per row:
```
attempt  fire_bias | jev_gate OFF  min_trades gate OFF  BT Jev off/mock  mean entry_thr (parents 1.50)
1        0.25      |     38%             49%                 11%              1.36
3        0.55      |     48%            100%                 10%              1.20
4        0.70      |    100%            100%                 10%              1.12
5        0.85      |    100%            100%                100%              1.04
```
The `jev_gate` frequency in your population therefore measures how many nursery retries happened (which F3 made universal), not whether gating helps. On top of that, `loop.py` forces `bt_jev_mode="mock"` for the first three attempts (`early_retry_jev_mode`), and the mean seat takes 1.4 attempts in simulation, so most graduates were examined against fabricated Jev answers.

**Patch:** nothing may rewrite a child's genes between inheritance and evaluation. If you want a prior toward firing, put it in the mutation distribution, symmetric and declared.

### F12 — The examinee writes the exam (MEASURED)

`backtest.py:66-108` clamps the numeric graduation thresholds but takes `use_min_trades`, `use_min_pnl`, `use_max_dd`, `use_hit_rate` straight from the organism's genes, with no floor. `evolution.py:471-478` flips them by mutation. `bt_jev_mode` and `bt_jev_max_calls` are genes too, so a child also chooses its own judge. `min_net_pnl_floor` is −$50.

`repro_F12_heritable_exam.py`, the same 300 children backtested twice, only the gene differs:
```
min_pnl gate ARMED   : pass 128/300 = 43%
min_pnl gate DISARMED: pass 297/300 = 99%
```
In a 25-cadence run of the shipped `EvoBot` (mock Jev, synthetic tape), seeds started 14/14 gated with every exam gate armed. Of 50 seated children: 18 kept `jev_gate`, 8 kept the min-trades gate, 25 kept the PnL gate, 30 kept the drawdown gate. The nursery breeds for exam evasion, which is what any selector does when the test is heritable.

**Patch:** evaluation criteria live in config, outside the genome.

### F13 — Graveyard clamps: no base rate, one direction (READ)

`mine_graveyard_clamps` (`evolution.py:154-205`) fires when ≥75% of the last 20 deaths share a trait. It never compares against how common the trait is among the living, so any majority trait looks lethal. F10 makes most children ungated, so most deaths are ungated, so `jev_gate_off` fires and forces `jev_gate=True` for five cadences. It fired three times in the simulation above, where Jev answers were mock and gating carried no information. `fire_bias` then forces the gate back off at attempt ≥4. Two controllers fight over one gene, both driven by artifacts, and Premium is computed on the result.

The detector list is also asymmetric: `jev_gate_off`, `jev_toxic_max_high`, `jev_spam_max_high`. All three Jev detectors can only push toward more Jev obedience. None can push away. Like α and β, that is a thumb on the scale of the experiment. The graveyard also holds F3's one-round-trip nursery verdicts and F11's false deaths.

**Patch:** enrichment ratio (share among deaths ÷ share among the living) with an interval, two-sided detectors.

### F14 — One gene, several units (READ)

`entry_threshold` is a z-score for mean reversion (seeds 0.7–1.0), a percent return for momentum (0.10–0.20), a per-mille EMA spread for micro-trend, and unused by breakout and fade (their seeds carry 0.18–0.30 anyway). Crossover averages it across parents of different thesis in the same island, and a thesis flip carries it into the wrong unit system. A mean-reversion × fade cross averages a z of 0.85 with an inert 0.30: the child enters at about half a standard deviation, a setting no ancestor was ever selected on. The genome has ~50 fields and most are inert for any given organism (EMA genes for MR, 15 Jev genes when ungated, Twitter genes), against 7 seats per island, so drift dominates.

**Patch:** thesis-scoped typed genomes; cross only like with like.

### Smaller notes (READ)

- `bump_idle_cadences` uses lifetime `n_trades` (`evolution.py:720-731`): one fill ever and an organism is never idle again.
- Breed midwife (`evolution.py:400-408`) and the meta-critics (`meta_critic.py:136-150`) build questions with `question`/`choices` keys. The client forwards questions verbatim, and the Decisions schema uses `instructions`/`criteria`. The mock answers `"other"` to both. If the live API validates, these calls fail into a bare `except` and fall back silently. Check ledger rows with `phase` breed or critic for `mocked` and real model ids. That would also explain a critic hit rate near 1.0.
- `spawn_child` nudges every child toward SOL's tape (`vol_fit_symbol="SOL"`) whichever mint it trades.
- README and MISSION describe 10 organisms (5+5) with `micro_trend` and `heat_scalp` seeds. Code and `config.yaml` have 14 (7+7); no seed or thesis pool uses `micro_trend`, so `signal_micro_trend` is unreachable.

---

## Dashboard

### What is good

- The theory bullets are generated deterministically from the genome. No LLM prose, nothing to hallucinate. That is honest explainability.
- Escaping is consistent (`esc()` on every interpolated string), it binds to 127.0.0.1, and the review pack copies an explicit allowlist of files with a manifest and a `README_FOR_AI`. No path to leaking `.env`.
- The nursery cell is good design: sparkline, then one row per gate marked pass, fail or **off**. F12 was on screen the whole time.
- Single file, no build step, charts rendered only when opened. The petri-dish language maps cleanly onto the data.

### F11 — Not read-only, and the writes do not stick (MEASURED)

`dashboard.py:746-818` exposes `POST /api/nursery/{id}/run|graduate|discard`. Each does load → modify → save on `population.json`. The loop reads that file once at startup (`loop.py:91`) and rewrites it from memory at the end of every poll (`loop.py:367`). No lock, no reload. `repro_F11_dashboard_lost_update.py` drives the real app and a real `EvoBot` on one scratch dir:
```
click Discard   : HTTP 200 {'ok': True, 'lifecycle': 'discarded'} -> organism gone from disk
graveyard file  : written
after next poll : organism back on disk, alive and trading
```
The click succeeds, the UI confirms it, and within one poll the loop reverts it. The graveyard keeps a death record for a living organism, which `mine_graveyard_clamps` then reads (F13). Neither endpoint checks lifecycle, so Discard works on a live trading organism. `/run` executes a backtest inside the dashboard process and can spend on the Jev key. The report's own rule #19 says the dashboard is a read-mostly observer.

**Patch:** GET only. If you want actions, write an intent file the loop consumes at a safe point.

### F15 — It headlines the broken numbers and cannot show the real failures (READ)

- The largest number on every cell, and the border color, are `fitness`. Under F9 the colony's one consistent winner renders as its sickest cell and never-traders look healthy. The header chip is Jev Premium (F9, F10, F13). Critic cards lead with hit rate.
- There is no mark-to-market anywhere. `_organism_row` (`dashboard.py:240-292`) carries no current price, unrealized PnL or position age. `equity_approx` is mark-to-entry and double-counts short proceeds (`models.py` `equity`: a $100 short on $2,000 reports $2,200), and the front end does not render it. A position stuck by F1 or F2 displays as "PnL −0.26, cash $2,100".
- It shows latest values, never distributions. The nursery board lists only cells incubating right now, which with auto-graduate is usually none, so ~140 nursery reports were never visible together. A histogram of fills per backtest would have been a single spike at 2. F3 would have been obvious at a glance.
- "Jev gate: off" appears on organisms whose orders are still blocked by `hard_safety` and sized by the Jev multiplier. The organism modal shows the colony's last Jev answer, whoever it was for.
- The review pack omits what an auditor needs most: nursery reports, the Jev ledger, a config snapshot and the git SHA (`bot_version` is the constant `0.1.0`).

### F16 — `EVO_BOT_DATA_DIR` does not relocate state (READ)

`config.py:322-337`: the variable sets `paths.data_dir` only. `population_file`, `trades_file`, `cadences_file`, `graveyard_dir`, `nursery_dir`, the ledger and the price pool stay under `<repo>/data`. A second instance started with a different `EVO_BOT_DATA_DIR` shares and overwrites the live population, and with `EVO_BOT_FORCE_SYNTHETIC=1` it appends synthetic ticks to the real pool (F6). Found when the first draft of the F11 repro wrote into the repo's `data/`.

---

## What carries into v2

I marked both modules DELETE before reading them. Revised:

**Evolution → extract the operators, rewrite the orchestration.** `crossover_params`, the `MUTATION_NOISE` tables, island multipliers, clamp ranges, heritage cards and the expiring-clamp idea are reusable (~200 lines). Four things change: the objective is replay over the full tape with walk-forward splits; genomes are thesis-scoped and contain nothing about how their carrier is evaluated; nothing edits genes between inheritance and evaluation; graveyard inference compares the dead against the living.

**Dashboard → keep the language, change what it watches.** Keep the single-file build, the dish, deterministic theory text, escaping, and the review pack (add SHA, config, nursery reports, ledger). Make it GET-only over replay outputs. Put invariant monitors above the fold, the ones that would have caught F1–F3: exit attempts vetoed (should be 0), positions older than their max hold, fills-per-backtest histogram, pool ticks by source, mark-to-market equity beside realized. Headline the paired Premium with its interval.

The dish itself transfers directly. In v2 the cells are **questions**: fitness is out-of-sample lift with an interval, the nursery is the dev split, the graveyard is the list of hypotheses that carried no information. Same metaphor, and this time the thing in the dish can actually be measured thousands of times a day.

## Not checked

`twitter_signal.py`, `meta_critic.py` beyond its question format, `vol_fit.py` internals, the dashboard in a real browser (reviewed from source), and anything requiring your `data/`. The 25-cadence figures come from a synthetic run with mock Jev, so they show what the machinery does by construction, not what happened in your live colony.
