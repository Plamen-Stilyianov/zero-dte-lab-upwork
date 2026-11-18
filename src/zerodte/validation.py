"""Chronological train/validation/test holdouts; freeze regime gating before validation.

No search/tuning of thresholds on holdout. No auto-deployment of model changes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .data import read_frames
from .engine import StrategyEngine
from .learn import regime_report
from .report import make_report


def run_holdout(data: str, c: Settings, train_end: date, val_end: date,
                out: str, delta_source: str = "provided") -> dict:
    if train_end >= val_end:
        raise ValueError("train_end must be before val_end")
    baseline_conf = replace(c, allow_model_gate=False)
    train = StrategyEngine(baseline_conf)
    val = StrategyEngine(baseline_conf)
    val_ungated = StrategyEngine(baseline_conf)
    test = StrategyEngine(baseline_conf)
    test_ungated = StrategyEngine(baseline_conf)
    permitted: dict[str, bool] | None = None
    tz = ZoneInfo(c.timezone)
    seen = {"train": set(), "validation": set(), "test": set()}
    for frame in read_frames(data, delta_source):
        day = frame.bar.ts.astimezone(tz).date()
        if day <= train_end:
            train.on_frame(frame)
            seen["train"].add(day)
        elif day <= val_end:
            if permitted is None:
                train.finalize()
                if train.incomplete:
                    raise ValueError("Training tape is incomplete; cannot freeze regime allowlist")
                # Persist frozen allowlist; exclude any same-day/training-future feedback.
                stats = regime_report(train.trades)
                permitted = {
                    regime: (s["n"] >= c.learning_min_trades
                             and s["pessimistic_edge_usd"] > c.learning_min_edge_usd)
                    for regime, s in stats.items()
                }
                val.fixed_regime_allowlist = permitted
                test.fixed_regime_allowlist = permitted
            val.on_frame(frame)
            val_ungated.on_frame(frame)
            seen["validation"].add(day)
        else:
            if permitted is None:
                raise ValueError("Dataset has no validation segment")
            test.on_frame(frame)
            test_ungated.on_frame(frame)
            seen["test"].add(day)
    if not all(seen.values()):
        raise ValueError("Dataset must contain train, validation and test days")
    engines = {"train": train, "validation_frozen": val,
               "validation_baseline": val_ungated, "test_frozen": test,
               "test_baseline": test_ungated}
    path = Path(out)
    path.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for name, engine in engines.items():
        if name != "train":
            engine.finalize()
        summaries[name] = make_report(engine, str(path / name), label=name)
    nval = summaries["validation_frozen"]["trades"]
    # Promotion must be manual, and a no-trade system cannot be claimed as successful.
    considered = bool(nval >= 30 and summaries["validation_frozen"]["complete_tape"]
                      and summaries["validation_frozen"]["pnl_usd_after_costs"] > 0)
    result = {
        "train_end": train_end.isoformat(), "validation_end": val_end.isoformat(),
        "session_days": {k: len(v) for k, v in seen.items()},
        "frozen_regime_allowlist": permitted, "validation_threshold_met": considered,
        "automatic_live_deployment": False,
        "notes": ["Validation selection must be frozen before untouched test data is examined.",
                  "Passing historical splits does not establish future edge.",
                  "Check tail losses, fill sensitivity and stability across volatility regimes."],
        "splits": summaries,
    }
    (path / "holdout.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
