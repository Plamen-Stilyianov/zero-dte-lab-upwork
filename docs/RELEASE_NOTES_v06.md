# v0.6 release notes — CPCV + Romano–Wolf

* Independent CPCV observation-level split planner with strict label interval
  purging, post-test embargoing, overlap checking, and SHA256 data manifest.
* Implements complete diagnostic path maps for even number of folds, k=2
  through round-robin one-factorization. No model training/return-stitching.
* Adds one-sided studentized Romano–Wolf stepdown on aligned daily return
  panels using synchronized stationary or circular block bootstrap, HAC
  long-run variance, finite-sample plus-one Monte Carlo correction.
* Adds incomplete-family detection when the declared number of historical
  trials exceeds the supplied strategy panel.
* New commands `cpcv-plan` and `romano-wolf`, synthetic demo label generator,
  regression tests, and detailed methodological caveats.
* Execution, broker connectivity, Greeks provenance, and initial 0DTE entry
  rules are unchanged. No real market data or profitability claims.

See `CPCV_ROMANO_WOLF_v06.md`.
