# exec-kpi-kit

**Executive KPI reporting, automated: metric definitions as code, a current-vs-prior-vs-target scorecard, rolling-baseline anomaly detection, and a plain-English executive summary — generated, tested, and reproducible end to end.**

Every company runs a version of the same weekly ritual: someone hand-builds a KPI deck, re-typing targets from a wiki page, copying numbers from three dashboards, and writing the "what happened" paragraph from memory. The numbers drift from the definitions, and nobody can re-run last week's deck. This project is the analytics-engineering answer to that ritual — the work analytics-engineering teams actually do: define each metric **once, as code** (a **metric registry** — a single declarative list where every KPI's formula, target, thresholds, and owner live), derive every report from those definitions, gate the data quality before anyone reads the numbers, and pin the whole pipeline with tests and golden evals so a changed definition fails loudly instead of quietly changing the story.

> **Synthetic data only.** Every figure is fabricated by a seeded generator for a fictional smart-home store (**Helios Home**). No real company, customer, or revenue data is used anywhere in this project.

Stdlib-only Python. Zero network, zero API keys, zero external dependencies.

## Quickstart

```bash
# 1. Generate the synthetic Helios Home dataset (90 days, seed 42)
python3 cli.py generate --out dataset.jsonl

# 2. List the metric definitions — the registry is the source of truth
python3 cli.py metrics

# 3. Scorecard: current period vs prior period vs target, per metric
python3 cli.py scorecard --input dataset.jsonl

# 4. Anomalies: days that break their rolling baseline, with evidence
python3 cli.py anomalies --input dataset.jsonl

# 5. Full report: scorecard + anomalies + executive narrative (JSON)
python3 cli.py report --input dataset.jsonl

# 6. CI gate: exit 0 = pass, 1 = metric breach (any red metric, or
#    anomalies above --max-anomalies), 2 = data-quality / IO error
python3 cli.py check --input dataset.jsonl

# 7. One-command end-to-end demo (generate -> scorecard -> narrative -> serve)
python3 demo.py

# 8. Tiny localhost API: GET /report, GET /scorecard, GET /health on 127.0.0.1
python3 cli.py serve --port 8765
```

## The seeded dataset at a glance (seed 42, 90 days, 2026-01-01 → 2026-03-31)

**$3,068,233.69** of revenue on **33,710** orders and **1,058,633** visitors. The generator plants three incidents so the detection has something real to find: a **revenue dip** on Mar 2–4 (traffic falls to ~55%), a **refund-rate spike** on Feb 15–16 (~2% → ~8.5%), and a **fulfilment blowout** on Jan 31 (24h → 49.5h) — on top of a steady +0.3%/day growth trend and a weekend traffic lift.

Scorecard — current period (Mar 2–31) vs prior period (Jan 31–Mar 1) vs target:

| Metric | Current | Prior | Δ | Target | Status |
|---|---|---|---|---|---|
| Revenue | $1,092,371.10 | $1,056,367.68 | +3.4% | $900,000 | 🟢 green |
| Orders | 11,564 | 11,564 | 0.0% | 10,500 | 🟢 green |
| Visitors | 365,383 | 361,125 | +1.2% | 330,000 | 🟢 green |
| Conversion rate | 3.16% | 3.20% | −1.2% | 3.20% | 🟡 yellow |
| Average order value | $94.46 | $91.35 | +3.4% | $88.00 | 🟢 green |
| Refund rate | 2.00% | 2.39% | −16.5% | ≤2.20% | 🟢 green |
| Support tickets | 905 | 924 | −2.1% | ≤800 | 🔴 red |
| Fulfilment time | 24.1h | 25.1h | −4.1% | ≤26h | 🟢 green |

Two stories hide in that table, and the narrative says both out loud: support tickets *improved* 2.1% and are still red, because status is judged against the target, not the trend — and orders are an exact tie (11,564 in both periods, a genuine coincidence of the seeded data, pinned by eval E2). The anomaly detector flags **12 days**, worst first: the refund spike (Feb 15, **z-score** — how many standard deviations a value sits from its baseline mean — of 42.45), the fulfilment blowout (z 29.0), and the revenue dip's first day across five metrics at once (Mar 2, revenue z −7.31). These numbers are pinned by golden evals, so any change to the generator, registry, or detector shows up as an eval failure, not a surprise.

## How it works

**Metric definitions as code.** Each of the 8 KPIs is one declarative entry in `metrics.py`: name, plain-English description, unit, **direction** (higher-is-better, or lower-is-better like refund rate), a formula, a 30-day target, warn/critical thresholds, and an owning team. The scorecard, the check gate, and the narrative all read this registry — change a target in one place and every report moves together. Two formulas deserve a callout because hand-built decks get them wrong: period conversion rate is *total orders ÷ total visitors* and period average order value is *total revenue ÷ total orders* — ratios of totals, never averages of daily ratios (eval E4 pins the distinction on a hand-computed case where the two methods disagree).

**Statuses.** Green/yellow/red are derived from the registry thresholds and the metric's direction: for higher-is-better, at-or-above target is green, at-or-above warn is yellow, below is red; lower-is-better mirrors it. A red value that has also crossed the critical threshold is flagged `beyond_critical`. Boundaries are pinned exactly (eval E5) in both directions.

**Anomaly detection.** Each daily series is judged against its own recent past: a **rolling baseline** — the mean and standard deviation of the previous 14 days — and a day is flagged when its |z-score| reaches 3.5, with the evidence attached (date, value, expected, z). The first 7 days are never judged; there is not enough baseline. One honest behaviour: a multi-day incident is flagged hardest on its *first* day, because the rolling baseline then absorbs the incident — the Mar 2 dip flags across five metrics, while Mar 3–4 flag more weakly. That is what a trailing baseline does, and the README says so rather than pretending otherwise.

**The narrative.** The executive summary is template-generated from the computed structures — headline status counts, the biggest period mover, every non-green metric named with its owner, and the anomaly callouts. No language model is involved, so the same dataset produces the same paragraph word for word (eval E9), and every number in the text is copied from the scorecard, never recomputed.

**Data quality first.** `validation.py` runs before any report: required fields, date continuity and duplicates, non-negative values, rate ranges, int/bool traps. It reports issues and never raises on bad data, so the `check` gate can map them to exit code 2 distinctly from a metric breach (exit 1).

## Architecture

| Module | Job |
|---|---|
| `metrics.py` | The registry: 8 declarative KPI definitions (formula, direction, target, warn/critical, owner) — the single source of truth every report derives from |
| `generator.py` | Deterministic synthetic Helios Home daily dataset (90 days): growth trend, weekend lift, three planted incidents; CSV / JSONL serialisers |
| `scorecard.py` | Current vs prior vs target per metric: period values from registry formulas, deltas, green/yellow/red status from thresholds + direction |
| `anomalies.py` | Rolling-baseline (14-day) z-score detector over 8 daily series, threshold 3.5, evidence-carrying flags, zero-variance sentinel |
| `narrative.py` | Deterministic template narrative (headline, top mover, at-risk metrics, anomaly callouts) + full report assembly |
| `validation.py` | Data-quality gate: required fields, date continuity/duplicates, non-negative and range checks — reports issues, never raises on bad data |
| `cli.py` | `generate` / `metrics` / `scorecard` / `anomalies` / `report` / `check` (CI exit 0/1/2) / `demo` / `serve` (stdlib `http.server` on 127.0.0.1: `GET /report`, `GET /scorecard`, `POST /report`, `POST /scorecard`, `GET /health`); CSV, JSONL, and JSON-array inputs |
| `demo.py` | End-to-end narrative with asserts: determinism, pinned statuses, planted incidents flagged, check exit codes, live localhost serve round-trip |
| `fixtures/` | The full seeded 90-day dataset (`sample_90d.jsonl` + `.csv`) with pinned totals |

## Evals

`python3 evals/run_evals.py` → **12/12 golden evals**, report committed at `evals/eval_report.json` (md5 `2d046b24338c1f18eda7228f22873b26`, byte-identical across 3 verified runs):

- **E1** generator determinism — seed 42 JSONL bytes pinned by md5
- **E2** scorecard pinned (6 green / 1 yellow / 1 red, revenue value, the exact orders tie)
- **E3** registry integrity — 8 metrics, thresholds ordered correctly per direction
- **E4** period formulas hand-computed (conversion is a ratio of totals, not a mean of ratios)
- **E5** status boundaries at target / warn pinned in both directions
- **E6** anomalies pinned (12 total; dip, refund spike, and fulfilment blowout all flagged)
- **E7** zero-variance baseline flags a spike with the sentinel z = 999.9
- **E8** validation flags planted defects; the generated dataset validates clean
- **E9** narrative deterministic, headline counts and worst-anomaly callout pinned
- **E10** CLI `check` exit codes 0 / 1 / 2
- **E11** serve round-trip matches local scorecard + report exactly
- **E12** bundled fixture pinned (90 days, total revenue $3,068,233.69, validates clean)

Unit tests: `python3 -m unittest discover -s tests` → **104 hermetic tests**, including a no-network enforcement test (sockets stubbed), registry integrity, hand-computed formulas, status logic in both directions, the anomaly detector on planted and clean data, narrative determinism and content, validation defects, CLI exit codes, JSON/CSV round-trips, and serve round-trips.

## Development loop — what the checks actually caught

1. **Real bug: the detector was blind to spikes on a flat baseline.** The first detector version skipped any day whose baseline standard deviation was 0 — which sounds safe, until the planted-spike tests failed: against a perfectly constant baseline, a revenue spike to $200,000 was *never flagged*, because the code treated "no variance" as "cannot judge" instead of "any deviation is maximally surprising". Fixed: a deviation from a zero-variance baseline is flagged with z = ±999.9, a documented sentinel (the true z is unbounded, and a literal infinity is not JSON-safe). Pinned by a unit test and eval E7.
2. **The first threshold cried wolf.** At the initial z ≥ 2.5, the detector flagged 38 of 90 days — the weekend traffic lift and the growth trend kept tripping the trailing baseline, burying the real incidents in noise. The threshold was tuned to 3.5 against the seeded data, landing at 12 flags with all three planted incidents caught. The tuning is documented here rather than hidden, because threshold choice *is* the product decision in anomaly detection.
3. **A test's own premise was wrong, and fixing it made the suite better.** The "small wiggle is not flagged" test originally used a perfectly flat baseline — after the zero-variance fix, *any* wiggle on a flat baseline correctly flags. The test now uses a realistically varied baseline, which is the case that actually matters in production data.

## Scope and honest limits

- **The detector is a trailing baseline, not a forecaster.** It has no seasonality model: the weekend lift is handled only by the tuned threshold, and a sustained incident gets absorbed into the baseline after its first days. A production system would compare like-for-like weekdays or fit a seasonal model.
- **Targets and thresholds are documented judgement**, chosen so the seeded book produces a realistic mix (6 green / 1 yellow / 1 red). They are the kind of numbers a business negotiates quarterly — the kit's claim is that they live in exactly one place, not that these particular values are right.
- **Periods are simple trailing blocks** (last 30 days vs the 30 before). No fiscal calendars, no partial-period handling, no cohort cuts.
- **The API is a demo surface.** It binds 127.0.0.1 only, holds its dataset in memory, and resets on restart.

## Why this project

It takes the author's day-job craft — marketing and portfolio analytics: GA4 reporting, KPI definitions argued over in decks, weekly business reviews — and rebuilds it as an analytics-engineering artifact: definitions as code, a data-quality gate, a tested scorecard and detector, and a narrative a VP could read verbatim. The same discipline a forward-deployed engineer brings to a customer problem: make the logic inspectable, make the outputs reproducible, and make the failure modes exit codes.
