# Free options data and research Greek computation — v0.4

**Scope:** SPY/QQQ US equity ETF options, 0DTE. **No funded orders, no broker paper orders, no data redistribution.**

## Reality check, November 2026

The existence of an open GitHub ingestion pipeline or a public SQL database does **not** make OPRA NBBO ticks, sub-second historical bid/ask, and timestamp-matched intraday Greeks freely available or licensed to redistribute.

| Candidate | Actually provides | Cannot supply for this project |
|---|---|---|
| DoltHub `post-no-preference/options` | Public `option_chain` plus `volatility_history` tables; queried using REST API | Subsecond history, option trade volume, quote provenance, complete executable US options book |
| QuantConnect Free cloud | Cloud LEAN research + backtests at **minute/higher** resolutions; US equity options dataset | Local QC data download, genuinely subsecond historical option backtests, off-platform export |
| `piekstra/options-data` | Rust storage / population tool with 5m bars via Alpaca credentials | Free prepackaged history, 1s NBBO data, stored Greeks |
| `pfmoro/Black-Scholes-Greeks` | Pricing/Greek formula reference | Market quotes, verified IV, American-style early exercise |
| `mcdallas/wallstreet` | Library to query market information and calculate Greeks | Historical, point-in-time 0DTE NBBO and verified replay feeds |
| `sajal101agrawal/nse-options-last-5-years` | Indian NSE F&O historical research infrastructure | US SPY/QQQ equity-option history |

**DoltHub correction:** A separate published July 2026 reconnaissance (see below) reports `option_chain` fields `date, act_symbol, expiration, strike, call_put, bid, ask, vol (implied volatility), delta, gamma, theta, vega, rho` — **`vol` is IV, not traded volume**. No quote sizes, option volume, trade timestamps, or open interest were found. Coverage was filtered and irregular; one tested date contained SPY entries but not QQQ. The report says the default Dolt branch is `master`, and this adapter uses `master`. We have **not independently queried the live database in this runtime**. The included bounded inspector lets you verify these claims before relying on them.

That EOD dataset can help compare day-level pricing or Greek distributions. Do **not** use daily snapshots to reconstruct option entry/exit prices for 0DTE trades or assume an EOD `date` is an intraday timestamp.

## New command: bounded public database inspector

```bash
# No API key required for public databases; requires outbound HTTPS on your machine.
zerodte inspect-dolthub --query tables --out results/free_data/tables.json
zerodte inspect-dolthub --query chain_schema --out results/free_data/chain_schema.json
zerodte inspect-dolthub --query chain_sample --out results/free_data/chain_sample.json
```

The SQL queries are intentionally fixed and read-only. No full dataset is fetched or cloned, no automatic mapping to trusted trading observations is available. Inspect the actual schema and the license/source terms before further use. `ref=master` is based on independent research, and may change; network or schema failures are explicit errors.

## New command: calculate local Greeks on true intraday input quotes

To use **your own legally obtained, point-in-time option bid/ask and underlying spot data**, prepare a CSV with:

`quote_ts,spot_ts,decision_ts,expiry_ts,option_symbol,right,spot,strike,bid,ask,rate,rate_observed_at,dividend_yield`

- All timestamps need explicit UTC offsets. `spot_ts <= quote_ts <= decision_ts`, `rate_observed_at <= quote_ts`; underlying and option quote observations must be within 60 seconds and option quote <=90 seconds old at decision time.
- Rates and dividend yield are *decimal fractions* (`0.04` means 4%), supplied as of the quote — never scrape a current Treasury yield and insert it into 2020 history. If you source US Treasury or FRED history, store actual **publication/availability** timestamp, not just economic observation date.
- Option quote needs same-session 0DTE expiry timestamp, not just a calendar date; holiday/half-day sessions need actual contract expiry calendar and no fabricated 16:00 close.
- Bid/ask must be noncrossed and strictly positive. There is no guarantee a bid/ask midpoint is executable.

```bash
zerodte enrich-greeks-research \
  --input data/your_legally_sourced_intraday_quotes.csv \
  --out results/free_data/local_greeks_research.csv \
  --reject-report results/free_data/greeks_rejects.json
```

This computes European Black-Scholes implied volatility by bisection, then delta, gamma, calendar-day theta, vega per 1 percentage-point volatility move, and rho per 1 percentage-point rate move. Uses the actual seconds between observation and explicit expiry rather than a fixed 0DTE year fraction. Each row is labeled `local_bs_research` and `RESEARCH_ONLY_NOT_EXECUTION_VERIFIED`. A failed inversion is **rejected**, never replaced with a fake 0.75 delta.

**American option warning:** SPY/QQQ ETF options are American-style, potentially exercisable before expiry and affected by dividends. European Black-Scholes is a baseline approximation; calibrating its volatility to an American put or dividend-sensitive call can bias IV and delta, particularly for deep ITM positions. A high-quality production check needs a tested American binomial/trinomial model, discrete dividend schedule, synchronized spot/option quotes and benchmark comparisons against an authorized vendor. The requested `abs(delta) >= 0.75` can amplify these issues.

**Never automatically turn these model estimates into `greek_provider=thetadata` or another trusted provider.** Existing `greek_policy=trusted` rejects them. Any exploratory simulation using `experimental` must remain separate from release approval and paper/live use.

## Free QuantConnect path without exporting their quotes

Use `examples/quantconnect/free_cloud_0dte_observer.py` as `main.py` in a new **QuantConnect Cloud** Python algorithm. It subscribes to 0DTE SPY options at minute resolution, checks contemporaneous chain prices and *intraday-computed* contract Greeks, prints a limited sample, and **never places an order**. It is an unexecuted starter and needs validation inside the current cloud runtime.

Cloud free access is not the same as an unlimited local data archive; QuantConnect's license restricts exporting cloud datasets outside the service. Preserve your 0DTE strategy's event-by-event structure in a separate LEAN backtesting research implementation when appropriate. Do not use daily precomputed **universe-filter** Greeks as the actual intraday delta.

## Source attribution

- [DoltHub database listing](https://www.dolthub.com/repositories/post-no-preference/options)
- [DoltHub SQL API v2](https://www.dolthub.com/docs/products/dolthub/api/v2/database/)
- [Independent July 2026 DoltHub schema / SPY coverage check](https://github.com/NavyBlueCheese/fx-vrp/blob/main/docs/data_availability.md) — third-party audit, not reverified live
- [QuantConnect tier features](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features)
- [QuantConnect equity options dataset](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/us-equity-options)
- [QuantConnect restrictions on exporting cloud data](https://www.quantconnect.com/docs/v2/cloud-platform/security-and-ip)
- [LEAN daily vs intraday Greeks](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/equity-options/greeks-and-implied-volatility/key-concepts)
- [piekstra/options-data](https://github.com/piekstra/options-data)
- [pfmoro/Black-Scholes-Greeks](https://github.com/pfmoro/Black-Scholes-Greeks)
- [mcdallas/wallstreet](https://github.com/mcdallas/wallstreet)
- [NSE research pipeline](https://github.com/sajal101agrawal/nse-options-last-5-years)
