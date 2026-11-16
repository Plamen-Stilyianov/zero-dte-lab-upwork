"""Auditable research decision log: hash chained JSONL, no broker credentials.

This is tamper-evident against partial edits, not tamper-proof. A writer who can
rewrite every record can reconstruct the whole chain; anchor the head externally
if stronger evidence is required.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
from typing import Any

ZERO = "0" * 64


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, default=_json_value).encode("utf-8")


def _json_value(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if is_dataclass(v):
        return asdict(v)
    raise TypeError(f"Cannot serialize: {type(v).__name__}")


def digest(payload: dict[str, Any]) -> str:
    return sha256(canonical(payload)).hexdigest()


def verify_ledger(path: str | Path) -> dict:
    file = Path(path)
    if not file.is_file():
        return {"verified": False, "count": 0, "head": ZERO, "error": "ledger_not_found"}
    prev = ZERO
    count = 0
    try:
        with file.open("rb") as reader:
            for line_no, raw in enumerate(reader, 1):
                if not raw.endswith(b"\n"):
                    raise ValueError("truncated_record")
                record = json.loads(raw)
                if not isinstance(record, dict) or set(record) != {"seq", "prev", "record", "hash"}:
                    raise ValueError("invalid_schema")
                content = {k: record[k] for k in ("seq", "prev", "record")}
                if record["seq"] != count + 1 or record["prev"] != prev:
                    raise ValueError("broken_sequence_or_link")
                if not isinstance(record["record"], dict) or digest(content) != record["hash"]:
                    raise ValueError("hash_mismatch")
                prev = record["hash"]
                count += 1
    except (ValueError, UnicodeError, TypeError, KeyError, json.JSONDecodeError) as err:
        return {"verified": False, "count": count, "head": prev,
                "error": str(err), "failed_line": count + 1}
    return {"verified": True, "count": count, "head": prev, "error": None,
            "warning": "Hash chain is locally rewritable without external anchoring."}


class DecisionLedger:
    """Single writer; validates existing record chain before appending.

    Uses a Linux advisory file lock and fsync for each high-level decision. Avoid
    logging per tick; on huge histories this should capture signals/fills only.
    """
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self._file = os.fdopen(fd, "r+b")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
        self._file.seek(0, 2)
        if self._file.tell():
            result = verify_ledger(self.path)
            if not result["verified"]:
                self.close()
                raise ValueError(f"Cannot append to corrupt ledger: {result['error']}")
            self.seq = result["count"]
            self.head = result["head"]
        else:
            self.seq = 0
            self.head = ZERO

    def append(self, kind: str, detail: dict[str, Any]) -> dict:
        if not kind or not isinstance(detail, dict):
            raise ValueError("kind and detail required")
        payload = {"kind": kind, "utc_logged_at": datetime.now(timezone.utc).isoformat(),
                   "detail": detail}
        content = {"seq": self.seq + 1, "prev": self.head, "record": payload}
        hashed = digest(content)
        row = dict(content, hash=hashed)
        raw = canonical(row) + b"\n"
        self._file.seek(0, 2)
        self._file.write(raw)
        self._file.flush()
        os.fsync(self._file.fileno())
        self.seq += 1
        self.head = hashed
        return row

    def close(self) -> None:
        if not self._file.closed:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()

    def __enter__(self) -> "DecisionLedger":
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
