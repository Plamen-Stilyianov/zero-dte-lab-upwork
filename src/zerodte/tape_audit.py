"""Streaming inspection of timestamped option quotes and Greek provenance.

This is a *schema/timing* audit. It never certifies whether vendor observations
are genuine NBBO, executable, complete, or the licensed feed a subscriber paid for.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from .config import Settings
from .data import read_frames
from .greeks_quality import delta_quality_reason


def audit_tape(path: str, c: Settings, delta_source: str = "provided",
               out: str | None = None) -> dict:
    providers: Counter[str] = Counter()
    quality: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    frames = 0
    total_quotes = 0
    with_reference = 0
    session_dates: set[str] = set()
    previous = None
    for frame in read_frames(path, delta_source):
        frames += 1
        now = frame.bar.ts
        if previous is not None and now < previous:
            raise ValueError("Global input timestamp order reversed")
        previous = now
        session_dates.add(now.astimezone(c_tz(c)).date().isoformat())
        symbols[frame.bar.symbol] += 1
        for quote in frame.quotes:
            total_quotes += 1
            with_reference += int(quote.reference_delta is not None)
            providers[quote.greek_provider or "missing"] += 1
            if quote.delta is not None and quote.expiry != now.astimezone(c_tz(c)).date():
                quality["not_0dte"] += 1
                continue
            if not quote.is_current(now, c.max_quote_age_seconds):
                quality["stale_or_future_quote"] += 1
                continue
            result = delta_quality_reason(quote, now, c)
            quality[result or "pass_provenance_and_time"] += 1
    report = {
        "kind": "data_quality_screen_not_market_data_verification",
        "input": path, "delta_source": delta_source,
        "greek_policy": c.greek_policy,
        "frames": frames, "quotes": total_quotes,
        "quotes_with_independent_reference": with_reference,
        "sessions": len(session_dates),
        "symbols": dict(symbols),
        "greek_providers": dict(providers),
        "timing_and_provenance": dict(quality),
        "warnings": [
            "A quality pass does NOT prove NBBO authenticity, data coverage or execution realism.",
            "Independently verify timestamp semantics, exchange calendars, quote sizes and vendor entitlements.",
            "Greek reference disagreement check occurs only when a separate reference_delta is supplied.",
            "CSV supplied with a Greek provider label is not cryptographically authenticated.",
            "This audit has not validated stock/option synchronization finer than timestamps in the tape.",
        ],
    }
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
    return report


def c_tz(c: Settings):
    from zoneinfo import ZoneInfo
    return ZoneInfo(c.timezone)
