"""Reproducible, scenario-based synthetic perturbations of a real/synthetic tape.

These are stress *tests*, not scientifically calibrated crash models. Most
recorded underlying bars and Greeks remain unchanged while the option quote
execution is degraded. Never use perturbed tapes to train a forecasting model.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import time
import json
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

from .config import Settings
from .data import read_frames
from .engine import StrategyEngine
from .models import Frame, OptionQuote
from .report import make_report


def perturb(frame: Frame, *, mode: str, rng: Random) -> Frame:
    if mode == "baseline" or mode == "delay_two_frames":
        return frame
    ny_time = frame.bar.ts.astimezone(ZoneInfo("America/New_York")).time()
    quotes: list[OptionQuote] = []
    for quote in frame.quotes:
        if mode == "liquidity_crisis":
            if time(10, 30) <= ny_time <= time(11, 30):
                # Suppress bids and sharply widen asks (stated synthetic shock).
                bid = max(0.01, round(quote.bid - 0.55, 4))
                ask = max(bid, round(quote.ask + 0.25, 4))
                quotes.append(replace(quote, bid=bid, ask=ask, volume=0))
            else:
                quotes.append(quote)
        elif mode == "price_gap":
            if time(11, 0) <= ny_time <= time(11, 4):
                bid = max(0.01, round(quote.bid - 0.90, 4))
                quotes.append(replace(quote, bid=bid))
            else:
                quotes.append(quote)
        elif mode == "random_execution_degradation":
            if rng.random() < .08:  # missing/late quote event
                continue
            # 0.1-1.5% spread slippage *stress* (not an estimated realistic range).
            rate = rng.uniform(.001, .015)
            bid = max(.01, round(quote.bid * (1 - rate), 4))
            ask = round(quote.ask * (1 + rate), 4)
            quotes.append(replace(quote, bid=bid, ask=ask))
        elif mode == "force_exit_disconnect":
            if time(15, 15) <= ny_time <= time(15, 30):
                continue
            quotes.append(quote)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    return Frame(frame.bar, tuple(quotes))


def run_adversarial(data: str, c: Settings, out: str,
                    delta_source: str = "provided", seed: int = 3891) -> dict:
    modes = ["baseline", "liquidity_crisis", "price_gap",
             "random_execution_degradation", "delay_two_frames", "force_exit_disconnect"]
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for mode in modes:
        rng = Random(seed)
        setting = replace(c, entry_delay_bars=max(2, c.entry_delay_bars)) if mode == "delay_two_frames" else c
        engine = StrategyEngine(setting)
        total = 0
        dropped_quotes = 0
        for frame in read_frames(data, delta_source):
            changed = perturb(frame, mode=mode, rng=rng)
            dropped_quotes += len(frame.quotes) - len(changed.quotes)
            engine.on_frame(changed)
            total += 1
        engine.finalize()
        summary = make_report(engine, str(root / mode), label=f"stress:{mode}")
        rows.append({"scenario": mode, "frames": total, "dropped_quote_events": dropped_quotes,
                     "entry_delay_bars": setting.entry_delay_bars,
                     "trades": summary["trades"],
                     "pnl_usd_after_costs": summary["pnl_usd_after_costs"],
                     "max_closed_trade_drawdown_usd": summary["max_closed_trade_drawdown_usd"],
                     "worst_trade_usd": summary["largest_trade_loss_usd"],
                     "complete_tape": summary["complete_tape"]})
    result = {"kind": "synthetic_execution_fault_injection_no_alpha_claim",
              "seed": seed, "real_market_history_supplied_by_user": False,
              "scenarios": rows,
              "warnings": [
                  "Input tape provenance must be verified separately; modes deliberately distort quotes.",
                  "Greek values are not recalculated under artificial quote shocks; do not use shocks as training data.",
                  "delay_two_frames measures one extra observed frame, NOT 50-500 millisecond latency.",
                  "Subsecond latency requires event-ordered subsecond bid/ask tick data; minute bars cannot support it.",
                  "Missing quotes can create incomplete positions; incomplete scenarios are failures, not wins.",
                  "Synthetic perturbations are not statistically estimated flash-crash/gamma or exchange fill models."]}
    (root / "adversarial.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
