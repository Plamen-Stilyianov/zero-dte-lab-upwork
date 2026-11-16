# v0.6 — CPCV split planning and studentized Romano–Wolf stepdown

> **Status:** independent research / statistical audit. This implementation does
> not establish real-data profitability, fill feasibility or real-money safety.
> No brokerage order integration or live-trading promotion has been added.

## Reviewed reference implementations

* `damiancclarke/rwolf` — Stata `rwolf`, studentized bootstrap Romano–Wolf
  correction with original estimates, bootstrap estimates and standard errors.
* `damiancclarke/rwolf2` — Stata `rwolf2`, more flexible multi-model command.
* `cran/wildrwolf` / `s3alfisc/wildrwolf` — R wild-cluster-bootstrap `fixest`
  implementation. Useful for cross-language verification of regression tests,
  **not** a drop-in method for autocorrelated daily trading returns.
* MetricGate Romano–Wolf overview — compact description of max-over-active
  stepdown correction. Treat claims about superiority to Holm as contextual;
  the finite-bootstrap comparison is not universally guaranteed.
* skfolio `CombinatorialPurgedCV` — practical documented CPCV API and warnings
  that CPCV paths can train on later chronological data.
* `eslazarev/purged-cross-validation` and `landtml/purgedcv` — standalone CPCV
  references with purging/embargoing and path construction ideas.
* Wilson Freitas' Awesome Quant — discovery catalog, not a statistical method.

This repository's v0.6 code is independent; no code from these libraries is
vendored and no Stata/R runtime is required.

## A. CPCV split plan

`zerodte cpcv-plan` reads a CSV with headers
`sample_id,start,end`, in chronological row order. Use UTC ISO 8601 timestamps
with `Z` or an explicit offset, or `YYYY-MM-DD` for a *daily-only research
example*. `end` is the latest instant of outcome-information availability, not
merely the exit timestamp if features or labels rely on additional events.

```bash
python scripts/make_cpcv_demo_labels.py \
  --returns-csv data/SYNTHETIC_statistical_panel.csv \
  --out data/SYNTHETIC_cpcv_labels.csv

zerodte cpcv-plan \
  --labels-csv data/SYNTHETIC_cpcv_labels.csv \
  --folds 6 --test-folds 2 --embargo 2 \
  --out results/v06_cpcv_synthetic.json
```

For N folds and k test folds, the splitter creates `C(N,k)` distinct tests.
Here `C(6,2) = 15`. It excludes overlapping outcome intervals from training,
then embargoes observations after selected test folds and their label horizons.
It checks that all train observations are disjoint from every test label
interval. Every split records excluded, trained and tested indices and the
original input SHA256. **Feature engineering, model fit, and option backtests
must be performed separately within each split.** This is only the split plan.

**Path reconstruction:** For even N and k=2, the planner provides N−1
round-robin diagnostic paths mapping exactly one test split to each fold.
No compounded returns are calculated or recombined here. Other N,k settings
produce valid split plans but currently no paths. Paths share historical
data and must not be mistaken for independent profitability trials.

**Not forward-only:** CPCV can train on later-period data relative to a test
fold. Continue using v0.5 walk-forward validation and a *frozen forward holdout*
for realistic chronology; CPCV is a robustness supplement, not a replacement.

## B. Formal studentized Romano–Wolf algorithm for synchronized daily returns

`zerodte romano-wolf` takes the existing v0.5 complete returns panel
(`session,strategy_id,daily_return`). All variants must have data for *every*
trade session including no-trade days. Inputs must be net of execution costs
and use consistent capital and mark-to-market conventions.

```bash
zerodte romano-wolf \
  --returns-csv data/SYNTHETIC_statistical_panel.csv \
  --iterations 1999 --method stationary \
  --block-length 6 --hac-lags 6 \
  --alpha 0.05 --seed 731 \
  --out results/v06_rw_synthetic.json
```

For each strategy j, we test the **one-sided** hypothesis that expected net
daily return is not positive, against a positive-mean alternative:
`H0: E[r_j] <= 0`, `H1: E[r_j] > 0`.

1. Compute `t_j = sqrt(n)*mean(r_j)/sqrt(HAC_LRV(r_j))` using Bartlett weighted
   Newey–West long-run variance on the complete daily returns.
2. Draw the *same* stationary (or circular) block-bootstrap daily indices for
   every strategy, preserving both short-lag serial dependence and
   contemporaneous correlation between strategy variants.
3. Form centered studentized replicates using `mean(r_j*) - mean(r_j)` and
   bootstrap-sample HAC variance. This is the joint estimated null law.
4. Order observed statistics from most to least positive. At step k, compare
   the current statistic with the **bootstrap maximum of all remaining active
   hypotheses**; add one to numerator/denominator for finite Monte Carlo.
5. Ensure adjusted p-values cannot decrease as hypotheses are removed.
   Report RW, unadjusted, single-step max-T, and Holm adjusted p-values.

This is a one-sided Romano–Wolf *stepdown implementation*, not the older v0.5
single-step max-T approximation. Its FWER interpretation is **conditional** on
valid bootstrap/studentization for this return process and on including the
complete research hypothesis family. It is not validated by a sample that was
used to choose among these same hypotheses.

If `--declared-trials` is larger than the number of supplied strategies, the
output explicitly sets `entire_declared_family_supplied=false` and suppresses
positive `pass_rw_alpha` decisions. Missing hypothesis outcomes cannot be
repaired by merely entering a bigger trial count.

### Deliberately out of scope

* Claiming CPCV itself proves live performance, or backtest paths are
  independent observations.
* General Romano–Wolf regression-coefficient testing, wild-cluster bootstrap,
  multiway clustering, double-sided testing, and arbitrary vector statistics.
* Automatic family discovery from past notebooks/LLM trials; callers must
  provide every trial, including earlier failed experiments.
* Automatic promotion to trading, broker execution, or investment decisions.
* Verification against Stata/R output on identical simulated datasets (the
  original projects can serve as external benchmarks for a paid quant audit).

### Sanity checks added

Tests cover split disjointness, overlapping outcome horizons, embargo after
multiple test folds, diagnostic path coverage, deterministic bootstrap results,
monotonic RW p-values, comparisons to unadjusted/single-step max-T p-values,
negative controls, and incomplete trial families.

## Sources

- https://github.com/damiancclarke/rwolf
- https://github.com/damiancclarke/rwolf2
- https://github.com/cran/wildrwolf
- https://metricgate.com/docs/romano-wolf-stepdown-multiple/
- https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html
- https://skfolio.org/user_guide/backtesting_and_evaluation.html
- https://github.com/eslazarev/purged-cross-validation
- https://github.com/landtml/purgedcv
- https://wilsonfreitas.github.io/awesome-quant/
