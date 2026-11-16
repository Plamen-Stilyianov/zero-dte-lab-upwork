"""24/7 READ-ONLY data watcher with local virtual paper fills.

No Alpaca orders are placed. Safe for research but not a live execution bot.
Stores a JSONL event tape; replays current session on process restart.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .alpaca import AlpacaDataError, AlpacaMarketData
from .config import load_settings
from .engine import StrategyEngine
from .models import Bar, Frame, OptionQuote, parse_ts
from .report import make_report

LOG = logging.getLogger("paper_watch")
NY = ZoneInfo("America/New_York")


def serialize_frame(f: Frame) -> dict:
    return {"bar": {"ts": f.bar.ts.isoformat(), "symbol": f.bar.symbol,
                    "close": f.bar.close, "high": f.bar.high, "low": f.bar.low,
                    "volume": f.bar.volume},
            "quotes": [{**asdict(q), "ts": q.ts.isoformat(), "expiry": q.expiry.isoformat()}
                       for q in f.quotes]}


def deserialize_frame(obj: dict) -> Frame:
    from datetime import date
    b = obj["bar"]
    bar = Bar(parse_ts(b["ts"]), b["symbol"], b["close"], b["high"], b["low"], b["volume"])
    quotes = []
    for entry in obj["quotes"]:
        entry = dict(entry)
        entry["ts"] = parse_ts(entry["ts"])
        entry["expiry"] = date.fromisoformat(entry["expiry"])
        quotes.append(OptionQuote(**entry))
    return Frame(bar, tuple(quotes))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.example.json")
    p.add_argument("--poll-seconds", type=int, default=10)
    args = p.parse_args()
    if args.poll_seconds < 5:
        p.error("poll-seconds must be >=5")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_settings(args.config)
    api = AlpacaMarketData()
    log_dir = Path("data")
    log_dir.mkdir(parents=True, exist_ok=True)
    engine = None
    processed = {}
    local_day = None
    printed_events = 0
    while True:
        now = datetime.now(timezone.utc)
        day = now.astimezone(NY).date()
        if day != local_day:
            if engine is not None:
                engine.finalize()
                make_report(engine, f"results/paper_sim_{local_day}", label="local_paper_sim")
            local_day = day
            engine = StrategyEngine(config)
            processed = {}
            printed_events = 0
            tape = log_dir / f"paper_sim_{day.isoformat()}.jsonl"
            if tape.exists():
                with tape.open(encoding="utf-8") as file:
                    for line in file:
                        item = json.loads(line)
                        observed = deserialize_frame(item["frame"])
                        if item.get("kind") == "monitor":
                            if engine.position is not None:
                                if item.get("early_close"):
                                    engine._exit(observed.quotes[0], observed.bar.ts, "early_close_or_holiday_guard")
                                else:
                                    engine._handle_position(observed)
                        else:
                            source = parse_ts(item["source_bar_ts"])
                            engine.on_frame(observed)
                            processed[observed.bar.symbol] = source
            printed_events = len(engine.events)
            LOG.info("Local simulator ready for %s; actual broker orders are DISABLED", day)
        try:
            clock = api.clock()
            if not clock.get("is_open", False):
                time.sleep(60)
                continue
            session_close = parse_ts(clock["next_close"])
            # Half-day safe entry cutoff; 30 minutes before actual broker close.
            is_close_buffer = now >= session_close - timedelta(minutes=30)
            for symbol in config.symbols:
                raw_start, b = api.latest_bar(symbol)
                if b.ts > now or (now - b.ts).total_seconds() > 90 or processed.get(symbol) == raw_start:
                    continue
                # Current observation time, not a fictional previous-minute fill timestamp.
                observed_bar = Bar(now, symbol, b.close, b.high, b.low, b.volume)
                market_quotes = () if is_close_buffer else tuple(api.chain(symbol, b.close, now))
                frame = Frame(observed_bar, market_quotes)
                # Append before state mutation; the replay is deterministic.
                with tape.open("a", encoding="utf-8") as file:
                    file.write(json.dumps({"kind": "frame", "source_bar_ts": raw_start.isoformat(),
                                           "frame": serialize_frame(frame)}) + "\n")
                engine.on_frame(frame)
                processed[symbol] = raw_start
            if engine.position:
                pos = engine.position
                # Exit monitoring runs independently of 1-minute bar triggers.
                _, b = api.latest_bar(pos.underlying)
                q = api.contract(pos.option, b.close)
                if q is not None and q.is_current(now, 20):
                    monitor = Frame(Bar(now, pos.underlying, b.close, b.high, b.low, b.volume), (q,))
                    with tape.open("a", encoding="utf-8") as file:
                        file.write(json.dumps({"kind": "monitor", "early_close": is_close_buffer,
                                               "frame": serialize_frame(monitor)}) + "\n")
                    if is_close_buffer:
                        engine._exit(q, now, "early_close_or_holiday_guard")
                    else:
                        engine._handle_position(monitor)
                elif is_close_buffer:
                    LOG.error("UNPRICED position near market close; simulated P&L incomplete")
                    engine.incomplete = True
            if len(engine.events) > printed_events:
                for event in engine.events[printed_events:]:
                    LOG.info("SIMULATION ONLY: %s", event)
                printed_events = len(engine.events)
            # A report snapshot each loop so a restart doesn't lose P&L history.
            make_report(engine, f"results/paper_sim_{day}", label="local_paper_sim")
        except (AlpacaDataError, KeyError, ValueError, OSError) as exc:
            LOG.error("FAIL CLOSED (no new entries when data is invalid): %s", type(exc).__name__)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
