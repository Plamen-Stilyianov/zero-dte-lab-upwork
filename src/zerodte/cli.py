"""Command line interface. Only backtest and local simulation are enabled by default."""
from __future__ import annotations

import argparse
import json

from .config import load_settings
from .data import read_frames
from .engine import StrategyEngine
from .report import make_report


def main() -> None:
    p = argparse.ArgumentParser(description="0DTE: research first, paper only")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backtest", help="Replay historical bid/ask quotes")
    b.add_argument("--data", required=True, help="CSV, Parquet file or directory")
    b.add_argument("--config", default="config.example.json")
    b.add_argument("--out", default="results/backtest")
    b.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    w = sub.add_parser("walk-forward", help="Chronological train/validation/test replay")
    w.add_argument("--data", required=True)
    w.add_argument("--config", default="config.example.json")
    w.add_argument("--train-end", type=str, required=True)
    w.add_argument("--validation-end", type=str, required=True)
    w.add_argument("--out", default="results/holdout")
    w.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    st = sub.add_parser("stress", help="Replay more pessimistic slippage scenarios")
    st.add_argument("--data", required=True)
    st.add_argument("--config", default="config.example.json")
    st.add_argument("--cents-per-side", default="0.02,0.05,0.10,0.20")
    st.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    st.add_argument("--out", default="results/stress")
    r = sub.add_parser("rolling", help="Expanding train/validation/test folds with session embargo")
    r.add_argument("--data", required=True)
    r.add_argument("--config", default="config.example.json")
    r.add_argument("--train-sessions", type=int, default=120)
    r.add_argument("--validation-sessions", type=int, default=30)
    r.add_argument("--test-sessions", type=int, default=30)
    r.add_argument("--step-sessions", type=int, default=30)
    r.add_argument("--embargo-sessions", type=int, default=1)
    r.add_argument("--max-folds", type=int, default=8)
    r.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    r.add_argument("--out", default="results/rolling")
    n = sub.add_parser("crosscheck-nautilus", help="Optional independent local Black-Scholes model check")
    n.add_argument("--data", required=True)
    n.add_argument("--out", required=True)
    n.add_argument("--interest-rate", type=float, default=0.04)
    n.add_argument("--dividend-yield", type=float, default=0.0)
    m = sub.add_parser("merge-tape", help="Align time-stamped vendor options CSV and underlying minute bars")
    m.add_argument("--bars", required=True)
    m.add_argument("--options", required=True)
    m.add_argument("--provider", required=True, choices=("thetadata", "orats", "cboe", "cboe_datashop", "broker_vendor"))
    m.add_argument("--mapping", default=None)
    m.add_argument("--out", required=True)
    q = sub.add_parser("audit-tape", help="Check Greek provenance, as-of time and historical tape integrity")
    q.add_argument("--data", required=True)
    q.add_argument("--config", default="config.example.json")
    q.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    q.add_argument("--out", default="results/data_quality.json")
    ap = sub.add_parser("adversarial", help="Fault injection: price gaps, dropouts, extra-frame latency")
    ap.add_argument("--data", required=True)
    ap.add_argument("--config", default="config.example.json")
    ap.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    ap.add_argument("--seed", type=int, default=3891)
    ap.add_argument("--out", default="results/adversarial")
    ar = sub.add_parser("audit-replay", help="Trace simulated entries/exits and signal decisions to a hash chain")
    ar.add_argument("--data", required=True)
    ar.add_argument("--config", default="config.example.json")
    ar.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    ar.add_argument("--ledger", default="results/replay/decisions.jsonl")
    ar.add_argument("--out", default="results/replay")
    av = sub.add_parser("verify-ledger", help="Verify complete chained decision journal")
    av.add_argument("--ledger", required=True)
    sc = sub.add_parser("scan-source", help="Conservative static temporal-leakage/dead-loop audit")
    sc.add_argument("--root", default="src/zerodte")
    sc.add_argument("--out", default="results/source_audit.json")
    bs = sub.add_parser("bootstrap", help="Exploratory session-block bootstrap on replay trade P&L")
    bs.add_argument("--data", required=True)
    bs.add_argument("--config", default="config.example.json")
    bs.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    bs.add_argument("--block", type=int, default=5)
    bs.add_argument("--iterations", type=int, default=1000)
    bs.add_argument("--seed", type=int, default=741)
    bs.add_argument("--out", default="results/bootstrap.json")
    er = sub.add_parser("export-return-panel", help="Complete-session trade reports -> comparable daily net return panel")
    er.add_argument("--tape", required=True, help="Underlying tape used for the complete session calendar")
    er.add_argument("--config", default="config.example.json")
    er.add_argument("--variant", action="append", required=True, help="Repeat NAME=path/to/trades.csv")
    er.add_argument("--capital", required=True, help="Common fixed research capital in USD")
    er.add_argument("--delta-source", choices=("provided", "estimated"), default="provided")
    er.add_argument("--out", default="results/returns_panel.csv")
    sa = sub.add_parser("statistical-audit", help="Family-wise return inference: block bootstrap, Holm/BH, PSR/DSR")
    sa.add_argument("--returns-csv", required=True, help="Long-form complete panel of session,strategy_id,daily_return")
    sa.add_argument("--selected", required=True, help="Frozen research candidate; not selected after seeing holdout")
    sa.add_argument("--out", default="results/statistical_audit.json")
    sa.add_argument("--method", choices=("stationary", "circular"), default="stationary")
    sa.add_argument("--block-length", type=int, default=None)
    sa.add_argument("--iterations", type=int, default=2000)
    sa.add_argument("--declared-trials", type=int, default=None)
    sa.add_argument("--seed", type=int, default=731)
    sa.add_argument("--alpha", type=float, default=0.05)
    sa.add_argument("--min-sessions", type=int, default=120)
    cp = sub.add_parser("cpcv-plan", help="Purged/embargoed CPCV split plan from point-in-time label intervals")
    cp.add_argument("--labels-csv", required=True, help="CSV: sample_id,start,end (UTC ISO timestamps)")
    cp.add_argument("--folds", type=int, default=6)
    cp.add_argument("--test-folds", type=int, default=2)
    cp.add_argument("--embargo", type=int, default=1, help="Observations after each test fold")
    cp.add_argument("--out", default="results/cpcv_splits.json")
    rw = sub.add_parser("romano-wolf", help="Studentized dependence-aware Romano-Wolf multiple-testing adjustment")
    rw.add_argument("--returns-csv", required=True, help="Complete daily return panel")
    rw.add_argument("--out", default="results/romano_wolf.json")
    rw.add_argument("--method", choices=("stationary", "circular"), default="stationary")
    rw.add_argument("--block-length", type=int, default=None)
    rw.add_argument("--hac-lags", type=int, default=None)
    rw.add_argument("--iterations", type=int, default=1999)
    rw.add_argument("--declared-trials", type=int, default=None)
    rw.add_argument("--seed", type=int, default=731)
    rw.add_argument("--alpha", type=float, default=0.05)
    rw.add_argument("--min-sessions", type=int, default=120)
    d = sub.add_parser("inspect-dolthub", help="Read-only schema/sample inspection; NOT a market data downloader")
    d.add_argument("--query", choices=("tables", "chain_schema", "volatility_schema", "chain_sample"),
                   default="chain_schema")
    d.add_argument("--out", default="results/free_data/dolthub_inspection.json")
    g = sub.add_parser("enrich-greeks-research", help="Compute research-only European Greeks from synchronized quotes")
    g.add_argument("--input", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--reject-report", default="results/free_data/greek_rejections.json")
    a = sub.add_parser("audit", help="Run adversarial/static checks (optionally with LLM)")
    a.add_argument("--llm", action="store_true")
    args = p.parse_args()
    if args.command == "export-return-panel":
        from .return_export import export_returns
        print(json.dumps(export_returns(args.tape, args.config, args.variant,
                                        args.capital, args.out, args.delta_source), indent=2))
        return
    if args.command == "statistical-audit":
        from .statistical_audit import audit_csv
        result = audit_csv(args.returns_csv, args.selected, args.out,
                           iterations=args.iterations, method=args.method,
                           block_length=args.block_length, alpha=args.alpha,
                           seed=args.seed, declared_trials=args.declared_trials,
                           min_sessions=args.min_sessions)
        print(json.dumps({"session_count": result["session_count"],
                          "present_variants": result["present_variants"],
                          "selected_strategy": result["selected_strategy"],
                          "selected_exploratory_statistical_screen": result["selected_exploratory_statistical_screen"],
                          "can_promote_to_live": False, "report": args.out}, indent=2))
        return
    if args.command == "cpcv-plan":
        from .cpcv import cpcv_csv
        result = cpcv_csv(args.labels_csv, args.out, n_folds=args.folds,
                          n_test_folds=args.test_folds, embargo_observations=args.embargo)
        print(json.dumps({"split_count": result["split_count"], "path_count": len(result["paths"]),
                          "can_promote_to_live": False, "report": args.out}, indent=2))
        return
    if args.command == "romano-wolf":
        from .romano_wolf import romano_wolf_csv
        result = romano_wolf_csv(args.returns_csv, args.out, iterations=args.iterations,
                                 method=args.method, block_length=args.block_length, lags=args.hac_lags,
                                 declared_trials=args.declared_trials, seed=args.seed,
                                 alpha=args.alpha, min_sessions=args.min_sessions)
        print(json.dumps({"session_count": result["session_count"],
                          "supplied_strategy_count": result["supplied_strategy_count"],
                          "entire_declared_family_supplied": result["entire_declared_family_supplied"],
                          "can_promote_to_live": False, "report": args.out}, indent=2))
        return
    if args.command == "inspect-dolthub":
        from .free_data import inspect_dolthub
        print(json.dumps(inspect_dolthub(args.query, args.out), indent=2))
        return
    if args.command == "enrich-greeks-research":
        from .greeks_lab import enrich_research_csv
        print(json.dumps(enrich_research_csv(args.input, args.out, args.reject_report), indent=2))
        return
    if args.command == "audit":
        from pathlib import Path
        import subprocess
        script = Path(__file__).resolve().parents[2] / "scripts" / "audit.py"
        cmd = ["python", str(script)] + (["--llm"] if args.llm else [])
        raise SystemExit(subprocess.run(cmd, check=False).returncode)
    if args.command == "crosscheck-nautilus":
        from .nautilus_reference import crosscheck_csv
        print(json.dumps(crosscheck_csv(args.data, args.out,
                                        args.interest_rate, args.dividend_yield), indent=2))
        return
    if args.command == "merge-tape":
        from .vendor_merge import load_mapping, merge_vendor_csv
        print(json.dumps(merge_vendor_csv(args.bars, args.options, args.out,
                                         args.provider, load_mapping(args.mapping)), indent=2))
        return
    if args.command == "verify-ledger":
        from .audit_ledger import verify_ledger
        result = verify_ledger(args.ledger)
        print(json.dumps(result, indent=2))
        if not result["verified"]:
            raise SystemExit(1)
        return
    if args.command == "scan-source":
        from .source_audit import scan_source
        print(json.dumps(scan_source(args.root, args.out), indent=2))
        return
    conf = load_settings(args.config)
    if args.command == "audit-replay":
        from .audit_replay import trace_replay
        result = trace_replay(args.data, conf, args.ledger, args.out, args.delta_source)
        print(json.dumps({"frames": result["frames"], "trades": result["trades"],
                          "ledger_status": result["ledger_status"]}, indent=2))
        return
    if args.command == "adversarial":
        from .adversarial import run_adversarial
        print(json.dumps(run_adversarial(args.data, conf, args.out, args.delta_source, args.seed), indent=2))
        return
    if args.command == "bootstrap":
        from .rolling import session_calendar
        from .statistics import from_trades, write_statistics
        engine = StrategyEngine(conf)
        for frame in read_frames(args.data, args.delta_source):
            engine.on_frame(frame)
        engine.finalize()
        if engine.incomplete:
            raise ValueError("Cannot evaluate incomplete tape with unresolved open trades")
        dates = session_calendar(args.data, conf, args.delta_source)
        result = from_trades(engine.trades, dates, args.block, args.iterations, args.seed,
                             conf.timezone)
        write_statistics(result, args.out)
        print(json.dumps(result, indent=2))
        return
    if args.command == "stress":
        from .stress import run_slippage_stress
        scenarios = [float(v.strip()) for v in args.cents_per_side.split(",")]
        print(json.dumps(run_slippage_stress(args.data, conf, scenarios,
                                            args.out, args.delta_source), indent=2))
        return
    if args.command == "audit-tape":
        from .tape_audit import audit_tape
        print(json.dumps(audit_tape(args.data, conf, args.delta_source, args.out), indent=2))
        return
    if args.command == "rolling":
        from .rolling import run_rolling
        result = run_rolling(args.data, conf, args.train_sessions, args.validation_sessions,
                             args.test_sessions, args.step_sessions, args.out,
                             args.delta_source, args.embargo_sessions, args.max_folds)
        print(json.dumps({k: v for k, v in result.items() if k != "folds"}, indent=2))
        return
    if args.command == "walk-forward":
        from datetime import date
        from .validation import run_holdout
        result = run_holdout(args.data, conf, date.fromisoformat(args.train_end),
                             date.fromisoformat(args.validation_end), args.out, args.delta_source)
        print(json.dumps(result, indent=2))
        return
    engine = StrategyEngine(conf)
    count = 0
    try:
        for frame in read_frames(args.data, args.delta_source):
            engine.on_frame(frame)
            count += 1
    finally:
        engine.finalize()
    summary = make_report(engine, args.out)
    print(json.dumps({"frames": count, **summary}, indent=2))


if __name__ == "__main__":
    main()
