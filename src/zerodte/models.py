"""Typed market data and fills. Option quotes are executable sides, never mid fills."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timezone
import math
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def parse_ts(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("Timestamps MUST contain timezone offset")
    return d.astimezone(timezone.utc)


def valid_number(v: float) -> bool:
    return math.isfinite(v)


@dataclass(frozen=True)
class Bar:
    ts: datetime
    symbol: str
    close: float
    high: float
    low: float
    volume: int

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None or self.ts.utcoffset() is None:
            raise ValueError("Bar timestamp must be timezone-aware")
        if (not all(valid_number(x) for x in (self.close, self.high, self.low))
                or min(self.close, self.high, self.low) <= 0 or self.low > self.high
                or not self.low <= self.close <= self.high or self.volume < 0):
            raise ValueError("Invalid OHLCV")


@dataclass(frozen=True)
class OptionQuote:
    ts: datetime
    symbol: str
    underlying: str
    expiry: date
    right: str
    strike: float
    bid: float
    ask: float
    delta: float | None
    volume: int
    multiplier: int = 100
    greek_provider: str | None = None
    delta_ts: datetime | None = None
    reference_delta: float | None = None
    reference_delta_ts: datetime | None = None
    reference_provider: str | None = None

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None or self.ts.utcoffset() is None:
            raise ValueError("Quote timestamp must be timezone-aware")
        if self.right not in ("C", "P") or not self.symbol or not self.underlying:
            raise ValueError("Invalid contract")
        if (not all(valid_number(x) for x in (self.bid, self.ask, self.strike))
                or self.bid <= 0 or self.ask < self.bid or self.strike <= 0
                or self.volume < 0 or self.multiplier != 100):
            raise ValueError("Invalid quote; nonstandard multipliers are rejected")
        if self.delta is not None and (not valid_number(self.delta) or not -1 <= self.delta <= 1):
            raise ValueError("Invalid delta")
        if self.reference_delta is not None and (
                not valid_number(self.reference_delta) or not -1 <= self.reference_delta <= 1):
            raise ValueError("Invalid independent reference delta")
        for timestamp in (self.delta_ts, self.reference_delta_ts):
            if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
                raise ValueError("Greek timestamps must be timezone-aware")
        if self.greek_provider is not None and not self.greek_provider.strip():
            raise ValueError("Greek provider must not be blank")

    def is_current(self, now: datetime, max_age: int) -> bool:
        return 0 <= (now - self.ts).total_seconds() <= max_age


@dataclass(frozen=True)
class Frame:
    bar: Bar
    quotes: tuple[OptionQuote, ...]


@dataclass(frozen=True)
class Signal:
    underlying: str
    right: str
    regime: str
    observed_at: datetime
    volume_ratio: float
    strength: float


@dataclass
class Position:
    option: str
    underlying: str
    right: str
    regime: str
    entry_time: datetime
    entry_price: float
    qty: int
    current_stop: float
    max_bid: float
    entry_volume_ratio: float
    entry_delta: float
    # Options notional is distinct from risk at stop


@dataclass(frozen=True)
class Trade:
    option: str
    underlying: str
    right: str
    regime: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    qty: int
    pnl: float
    reason: str
    entry_delta: float
    entry_volume_ratio: float

    def as_dict(self) -> dict:
        return {
            "option": self.option, "underlying": self.underlying,
            "right": self.right, "regime": self.regime,
            "entry_time": self.entry_time.isoformat(), "exit_time": self.exit_time.isoformat(),
            "entry_price": round(self.entry_price, 4), "exit_price": round(self.exit_price, 4),
            "qty": self.qty, "pnl": round(self.pnl, 2), "reason": self.reason,
            "entry_delta": round(self.entry_delta, 4),
            "entry_volume_ratio": round(self.entry_volume_ratio, 3),
        }
