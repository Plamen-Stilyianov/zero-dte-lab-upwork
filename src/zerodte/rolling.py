"""Session-purged, expanding-window walk-forward evaluation for 0DTE.

Every validation/test pass recomputes an allowance using ONLY its own earlier
training sessions; the test is never used for training or selection. We do not
automatically declare a successful system or tune hyperparameters on the test.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .data import read_frames
from .engine import StrategyEngine
from .learn import regime_report
from .report import make_report


@dataclass(frozen=True)
class Fold:
    index: int
    train_end: date
    val_start: date
    val_end: date
    test_start: date
    test_end: date


def session_calendar(data: str, c: Settings, source: str) -> list[date]:
    dates: list[date] = []
    zone = ZoneInfo(c.timezone)
    last: date | None = None
    for frame in read_frames(data, source):
        current = frame.bar.ts.astimezone(zone).date()
        if last is not None and current < last:
            raise ValueError("Market sessions not chronological")
        if current != last:
            dates.append(current)
            last = current
    return dates


def make_folds(dates: list[date], train_sessions: int, validation_sessions: int,
               test_sessions: int, step_sessions: int, embargo_sessions: int = 1) -> list[Fold]:
    if min(train_sessions, validation_sessions, test_sessions, step_sessions) < 1:
        raise ValueError("Session windows and step must be positive")
    if not 0 <= embargo_sessions <= 10:
        raise ValueError("embargo must be 0..10 complete sessions")
    if sorted(set(dates)) != dates:
        raise ValueError("dates must be distinct and chronological")
    folds = []
    train_len = train_sessions
    while True:
        val_lo = train_len + embargo_sessions
        val_hi = val_lo + validation_sessions
        test_lo = val_hi + embargo_sessions
        test_hi = test_lo + test_sessions
        if test_hi > len(dates):
            break
        folds.append(Fold(len(folds) + 1, dates[train_len - 1],
                          dates[val_lo], dates[val_hi - 1],
                          dates[test_lo], dates[test_hi - 1]))
        train_len += step_sessions
    if not folds:
        raise ValueError("Insufficient sessions for expanding train/validation/test with embargo")
    return folds


def run_rolling(data: str, c: Settings, train_sessions: int, validation_sessions: int,
                test_sessions: int, step_sessions: int, out: str,
                delta_source: str = "provided", embargo_sessions: int = 1,
                max_folds: int = 8) -> dict:
    if not 1 <= max_folds <= 100:
        raise ValueError("max_folds must be 1..100")
    dates = session_calendar(data, c, delta_source)
    folds = make_folds(dates, train_sessions, validation_sessions,
                       test_sessions, step_sessions, embargo_sessions)
    # Predeclare the scope; do not pick successful folds after seeing outcomes.
    folds = folds[-max_folds:]
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    zone = ZoneInfo(c.timezone)
    results: list[dict] = []
    for fold in folds:
        base = replace(c, allow_model_gate=False)
        train = StrategyEngine(base)
        validation = StrategyEngine(base)
        test = StrategyEngine(base)
        test_baseline = StrategyEngine(base)
        allowlist = None
        for frame in read_frames(data, delta_source):
            day = frame.bar.ts.astimezone(zone).date()
            if day <= fold.train_end:
                train.on_frame(frame)
            elif fold.val_start <= day <= fold.val_end:
                if allowlist is None:
                    # Train is fully in the past and all later sessions are excluded.
                    stats = regime_report(train.trades)
                    allowlist = {name: (stat["n"] >= c.learning_min_trades
                                        and stat["pessimistic_edge_usd"] > c.learning_min_edge_usd)
                                 for name, stat in stats.items()}
                    validation.fixed_regime_allowlist = allowlist
                    test.fixed_regime_allowlist = allowlist
                validation.on_frame(frame)
            elif fold.test_start <= day <= fold.test_end:
                if allowlist is None:
                    raise ValueError("Missing validation period in fold")
                test.on_frame(frame)
                test_baseline.on_frame(frame)
            if day > fold.test_end:
                break
        folder = output / f"fold_{fold.index:02d}"
        for strategy in (train, validation, test, test_baseline):
            strategy.finalize()
        report = {
            "fold": fold.index,
            "train_end": fold.train_end.isoformat(),
            "validation_start": fold.val_start.isoformat(),
            "validation_end": fold.val_end.isoformat(),
            "test_start": fold.test_start.isoformat(),
            "test_end": fold.test_end.isoformat(),
            "purged_sessions_between_splits": embargo_sessions,
            "frozen_allowlist": allowlist,
            "train": make_report(train, str(folder / "train")),
            "validation": make_report(validation, str(folder / "validation")),
            "test": make_report(test, str(folder / "test")),
            "test_baseline": make_report(test_baseline, str(folder / "test_baseline")),
        }
        results.append(report)
    summary = {
        "kind": "expanding_rolling_forward_research_only",
        "data_sessions": len(dates),
        "fold_count": len(results),
        "automatic_live_deployment": False,
        "test_folds_with_trades": sum(r["test"]["trades"] > 0 for r in results),
        "test_total_pnl_usd_after_costs": round(sum(r["test"]["pnl_usd_after_costs"] for r in results), 2),
        "test_sum_trades": sum(r["test"]["trades"] for r in results),
        "warning": ("Rolling test windows may overlap if step_sessions < test_sessions. "
                    "Aggregate test P&L is not a portfolio result or independent-sample inference. "
                    "Fold tests are for diagnosis; selection decisions require a separate untouched final holdout."),
        "folds": results,
    }
    (output / "rolling.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
