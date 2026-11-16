"""Timestamped historical quote loader (CSV or chunked Parquet) with strict schema."""
from __future__ import annotations

import csv
from datetime import date
from itertools import groupby
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from .greeks import estimated_delta
from .models import Bar, Frame, OptionQuote, parse_ts

PROVENANCE = ("greek_provider", "delta_ts")
OPTIONAL_GREEKS = ("reference_delta", "reference_delta_ts", "reference_provider")

REQUIRED = (
    "ts", "underlying", "close", "high", "low", "volume",
    "option_symbol", "expiry", "right", "strike", "bid", "ask", "option_volume", "quote_ts",
)


def _records(path: str, delta_source: str) -> Iterator[Mapping[str, object]]:
    if path.endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None or set(REQUIRED) - set(reader.fieldnames):
                raise ValueError(f"Missing columns: {sorted(set(REQUIRED) - set(reader.fieldnames or []))}")
            if delta_source == "provided" and "delta" not in reader.fieldnames:
                raise ValueError("Point-in-time delta column missing; use --delta-source estimated to model")
            if delta_source == "provided" and set(PROVENANCE) - set(reader.fieldnames):
                raise ValueError("Provided Greeks require greek_provider and delta_ts columns; do not invent provenance")
            yield from reader
    elif path.endswith(".parquet") or Path(path).is_dir():
        try:
            import duckdb
        except ImportError as err:
            raise RuntimeError("For Parquet: pip install '.[parquet]'") from err
        con = duckdb.connect()
        con.execute("SET memory_limit='512MB'")
        con.execute("SET temp_directory='data/duckdb_tmp'")
        # Sorted output is necessary for streaming next-bar execution.
        source = f"{path.rstrip('/')}/**/*.parquet" if Path(path).is_dir() else path
        available = {v[0] for v in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source]).fetchall()}
        required = set(REQUIRED) | (set(("delta",) + PROVENANCE) if delta_source == "provided" else set())
        missing = required - available
        if missing:
            con.close()
            raise ValueError(f"Missing Parquet columns: {sorted(missing)}")
        selected = list(REQUIRED) + (["delta", *PROVENANCE] if delta_source == "provided" else [])
        selected += [field for field in OPTIONAL_GREEKS if field in available]
        select_cols = ", ".join(selected)
        cur = con.execute(f"SELECT {select_cols} FROM read_parquet(?) ORDER BY ts, underlying, option_symbol", [source])
        names = [desc[0] for desc in cur.description]
        try:
            while chunk := cur.fetchmany(20000):
                for values in chunk:
                    yield dict(zip(names, values))
        finally:
            con.close()
    else:
        raise ValueError("Data path must be .csv, .parquet, or a directory of Parquet files")


def _time_str(v: object) -> str:
    # DuckDB may return datetime objects; zoneinfo offsets must be preserved.
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _make_frame(rows: list[Mapping[str, object]], delta_source: str) -> Frame:
    first = rows[0]
    ts = parse_ts(_time_str(first["ts"]))
    bar = Bar(ts, str(first["underlying"]), float(first["close"]),
              float(first["high"]), float(first["low"]), int(first["volume"]))
    quotes = []
    for row in rows:
        if any(str(row[field]) != str(first[field]) for field in ("close", "high", "low", "volume")):
            raise ValueError("Inconsistent underlying bar across option rows for same minute")
        qt = parse_ts(_time_str(row["quote_ts"]))
        expiry = date.fromisoformat(_time_str(row["expiry"])[:10])
        bid, ask = float(row["bid"]), float(row["ask"])
        supplied = row.get("delta")
        if delta_source == "provided" and supplied not in (None, "", "None"):
            d = float(supplied)
        elif delta_source == "estimated":
            # bar.close is only point-in-time compatible with a quote stamped at
            # the *same* completed bar time. Using a newer bar close to value
            # an older option quote would leak future spot into the Greek.
            d = (estimated_delta(bar.close, float(row["strike"]), (bid + ask) / 2,
                                 str(row["right"]), qt) if qt == ts else None)
        else:
            d = None
        greek_provider = (str(row.get("greek_provider") or "") if delta_source == "provided"
                          else "local_bs_research")
        dts_raw = row.get("delta_ts") if delta_source == "provided" else qt
        dts = parse_ts(_time_str(dts_raw)) if dts_raw not in (None, "", "None") else None
        ref_raw = row.get("reference_delta")
        ref_delta = float(ref_raw) if ref_raw not in (None, "", "None") else None
        ref_time_raw = row.get("reference_delta_ts")
        ref_ts = (parse_ts(_time_str(ref_time_raw))
                  if ref_time_raw not in (None, "", "None") else None)
        if qt > ts:
            raise ValueError("Future option quote within historical bar: look-ahead leak")
        quotes.append(OptionQuote(qt, str(row["option_symbol"]), bar.symbol,
                                  expiry, str(row["right"]), float(row["strike"]),
                                  bid, ask, d, int(row["option_volume"]), 100,
                                  greek_provider, dts, ref_delta, ref_ts,
                                  str(row.get("reference_provider") or "") or None))
    return Frame(bar, tuple(quotes))


def read_frames(path: str, delta_source: str = "provided") -> Iterator[Frame]:
    if delta_source not in ("provided", "estimated"):
        raise ValueError("delta-source must be provided or estimated")
    rows: Iterable[Mapping[str, object]] = _records(path, delta_source)
    # Compare actual UTC instants, not lexical strings with possibly different offsets.
    # CSV is not implicitly sorted. For streaming input, groupby needs identical instants.
    last_key = None
    for key, group in groupby(rows, key=lambda x: (parse_ts(_time_str(x["ts"])), str(x["underlying"]))):
        if last_key is not None and key <= last_key:
            raise ValueError("Input must be strictly sorted by timestamp then underlying")
        last_key = key
        yield _make_frame(list(group), delta_source)
