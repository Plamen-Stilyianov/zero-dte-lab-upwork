"""Merge point-in-time vendor option exports with completed underlying minute bars.

This is an *importer*, NOT a downloader or a way to acquire licensed market data.
Both inputs must be sorted by observation timestamp and ticker; vendor field
names vary, so the option file may be mapped through an explicit JSON mapping.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Iterator

from .data import REQUIRED, PROVENANCE
from .models import parse_ts

OUTPUT = list(REQUIRED) + ["delta", *PROVENANCE, "reference_delta", "reference_delta_ts", "reference_provider"]
BAR_FIELDS = ("ts", "underlying", "close", "high", "low", "volume")
OPTION_FIELDS = ("ts", "underlying", "option_symbol", "expiry", "right", "strike",
                 "bid", "ask", "option_volume", "quote_ts", "delta", "delta_ts")


def _bar_key(row: dict) -> tuple[datetime, str]:
    return parse_ts(str(row["ts"])), str(row["underlying"])


def _rows(reader: csv.DictReader, kind: str) -> Iterator[dict]:
    last = None
    for row in reader:
        current = _bar_key(row)
        if last is not None and current < last:
            raise ValueError(f"{kind} input is not sorted by actual UTC timestamp and symbol")
        last = current
        yield row


def merge_vendor_csv(bars: str, options: str, out: str, provider: str,
                     option_columns: dict[str, str] | None = None,
                     bar_timestamp_convention: str = "bar_end") -> dict:
    """Stream-join matching completed minute bars and vendor option quote rows.

    'option_columns' maps canonical name -> source header name. It is intentionally
    explicit; undocumented vendor API formats must not be guessed.
    """
    if bar_timestamp_convention not in ("bar_end", "bar_start"):
        raise ValueError("bar_timestamp_convention must be 'bar_end' or 'bar_start'")
    bar_shift = timedelta(minutes=1) if bar_timestamp_convention == "bar_start" else timedelta(0)
    from .greeks_quality import VENDORS
    if provider.casefold().strip() not in VENDORS:
        raise ValueError("Use a known source label for real historical vendor data")
    columns = option_columns or {}
    output_path = Path(out)
    if output_path.resolve() in {Path(bars).resolve(), Path(options).resolve()}:
        raise ValueError("Output must not overwrite input")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(bars, newline="", encoding="utf-8") as bf, \
         open(options, newline="", encoding="utf-8") as of, \
         output_path.open("w", newline="", encoding="utf-8") as dst:
        br = csv.DictReader(bf)
        op = csv.DictReader(of)
        if not br.fieldnames or set(BAR_FIELDS) - set(br.fieldnames):
            raise ValueError("Underlying bars need ts, underlying, close, high, low, volume")
        if not op.fieldnames or any(columns.get(x, x) not in op.fieldnames for x in OPTION_FIELDS):
            raise ValueError("Vendor option export lacks fields required by explicit option mapping")
        bar_iterator = _rows(br, "bars")
        bar = next(bar_iterator, None)
        option_last = None
        writer = csv.DictWriter(dst, fieldnames=OUTPUT)
        writer.writeheader()
        for raw in op:
            r = {name: raw.get(columns.get(name, name), "") for name in OUTPUT}
            key = _bar_key(r)
            if option_last is not None and key < option_last:
                raise ValueError("Options export not sorted by observation UTC timestamp and underlying")
            option_last = key
            while bar is not None and (_bar_key(bar)[0] + bar_shift, _bar_key(bar)[1]) < key:
                bar = next(bar_iterator, None)
            if bar is None or (_bar_key(bar)[0] + bar_shift, _bar_key(bar)[1]) != key:
                raise ValueError(f"No completed underlying bar matching option observation {key}")
            if parse_ts(str(r["quote_ts"])) > key[0] or parse_ts(str(r["delta_ts"])) > key[0]:
                raise ValueError("Future quote or delta timestamp — look-ahead contamination")
            r.update({k: bar[k] for k in BAR_FIELDS if k not in ("ts", "underlying")})
            r["greek_provider"] = provider.casefold().strip()
            writer.writerow(r)
            written += 1
    return {"output": str(output_path), "option_rows": written,
            "provider_label": provider.casefold().strip(),
            "warning": "A provider label is asserted by the importer, not cryptographically verified. Run audit-tape."}


def load_mapping(path: str | None) -> dict[str, str]:
    if path is None:
        return {}
    obj = json.loads(Path(path).read_text())
    if not isinstance(obj, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                            for k, v in obj.items()):
        raise ValueError("Mapping must be a JSON object of canonical field names to vendor columns")
    if set(obj) - set(OUTPUT):
        raise ValueError(f"Unknown canonical mapping names: {sorted(set(obj) - set(OUTPUT))}")
    return obj
