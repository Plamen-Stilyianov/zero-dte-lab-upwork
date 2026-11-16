# Input contract v0.2: timestamped option and underlying observations

To be usable for 0DTE research, the dataset must not be an equity daily-price table or option OHLC bar without bid/ask. Inputs are observations, not daily hindsight. **The CSV's `ts` denotes the time by which the completed underlying bar and the option quote were available.** Every timestamp below is ISO 8601 with UTC offset.

## Required canonical columns

```
ts,underlying,close,high,low,volume,option_symbol,expiry,right,strike,bid,ask,option_volume,quote_ts,delta,greek_provider,delta_ts
```

- `ts` — UTC time at which the completed minute bar and option snapshot are known; sorted ascending. Never reinterpret bar-start as bar-end.
- `underlying` — SPY/QQQ ticker. The OHLCV fields must refer to a completed 1-minute bar, not an adjusted daily-close bar.
- `option_symbol` — unadjusted standard OCC contract code, `expiry` actual date, `right` C/P, `strike` decimal dollar price.
- `bid`, `ask`, `quote_ts` — observed option NBBO/executable-side quote and source timestamp, with `quote_ts <= ts` and a fresh quote, not a model midpoint or last trade.
- `option_volume` — running or trailing volume **as observed by `ts`**, not full-day volume known only at the end of the day.
- `delta`, `greek_provider`, `delta_ts` — contemporaneous vendor model delta, vendor name and computation/observation timestamp. `delta_ts` must be at or before `ts`, sufficiently close to the corresponding quote, and no more than 30 seconds old at default risk settings.

Optional:

```
reference_delta,reference_delta_ts,reference_provider
```

These represent a separate **named and time-aligned independent** calculation. When supplied, deltas must agree within 0.08 (configurable). Do not use a second field from the **same** vendor to claim independent confirmation. Comparison is a veto, not a weighted average.

Accepted `greek_provider` labels: `thetadata`, `orats`, `cboe`, `cboe_datashop`, `broker_vendor` under `trusted` policy. These are asserted source labels, not proof of provenance. `synthetic`, `nautilus_local`, or `local_bs_research` are allowed only in `experimental` policy. The default config uses `trusted`.

## Importing two aligned exports

Obtain licensed vendor option quote/Greek output plus completed 1-minute stock OHLCV from an independent stock-data feed. Normalize the source columns using a JSON field map as necessary. The importer does not fetch data or infer that a source field represents valid timing.

```bash
zerodte merge-tape \
  --bars /licensed/underlying_completed_1min.csv \
  --options /licensed/options_asof.csv \
  --provider thetadata \
  --mapping docs/example_option_field_mapping.json \
  --out data/research/tape.csv

zerodte audit-tape --data data/research/tape.csv --out results/tape_audit.json
```

`--mapping` maps **canonical column name to actual vendor export header**, such as `{"option_symbol":"contract_symbol"}`. The example mapping is only a template; it is **not** a claim about ThetaData field names. Adapt the map to the provider schema and confirm timestamps/exercise style before importing. Omit `--mapping` for already normalized option CSVs. The bar CSV must use `ts,underlying,close,high,low,volume` headers.

The importer requires **identical observation timestamps** for each option-row and its completed underlying bar. If your licensed feed gives subsecond quote events, resample as-of with a dedicated data-prep process first, without looking ahead. It fails if an underlying minute bar is missing or either Greek or quote comes from the future. Do **not** forward fill contract volume or Greeks indefinitely.

## 1-minute data limitation

A one-minute snapshot can miss a stop breach and recovery occurring between snapshots; using minute-level backtest P&L can seriously understate tail losses. Tick-level quote data, or a sufficiently conservative stress model, is needed before capital is considered. Even tick quotes cannot certify a particular fill or market impact. **An actual $0.40 premium stop is a trigger, not a contractual loss limit.**

## Vendor checks before data is considered usable

- Licensed feed type & data entitlement (including access to expired chains).
- NBBO bid/ask size and exchange condition; correct timestamp units/time zone.
- Quotes matched with point-in-time Greek computation; no current Greeks used on past quotes.
- SOFR/risk-free carry, dividend estimate, exercise style (SPY/QQQ are American); handle model misfit/IV error explicitly upstream.
- Source underlying volume/close as actually available, prior completed minutes only.
- Market half-days and closed days, adjusted corporate actions, nonstandard multipliers vetoed.
- No cherry-picked samples or post-selection of only profitable contract series.

**No genuine licensed option history is bundled with this project.**

## Optional NautilusTrader independent comparison

If you deliberately install the separate NautilusTrader dependency, you may add a local Black–Scholes reference delta to a **canonical vendor CSV**:

```bash
pip install nautilus_trader
zerodte crosscheck-nautilus --data data/research/tape.csv \
  --out data/research/tape_checked.csv --interest-rate 0.04 --dividend-yield 0.0
zerodte audit-tape --data data/research/tape_checked.csv
```

The example 4% interest and 0% dividend are **illustrative**, not correct universal market inputs. Choose as-of actual market assumptions and verify whether the vendor's IV/Greeks model is comparable. Nautilus's local BS solver is **European-style**; SPY/QQQ are American-style. A disagreement is a reason to investigate or veto an entry, not proof that either model is right. If IV solving fails, the reference is omitted, and that observation does **not** receive independent confirmation. The `greeks_quality` gate never averages the two deltas.
