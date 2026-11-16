"""Deterministic minute-close trigger. No future-bar leakage."""
from __future__ import annotations

from collections import deque
from datetime import date
from statistics import fmean

from .config import Settings
from .models import Bar, Signal


class TrendSignal:
    def __init__(self, config: Settings):
        self.c = config
        self.day: date | None = None
        self.volumes: deque[int] = deque(maxlen=config.volume_lookback)
        self.highs: deque[float] = deque(maxlen=config.breakout_lookback)
        self.lows: deque[float] = deque(maxlen=config.breakout_lookback)
        self.fast: float | None = None
        self.slow: float | None = None
        self.seen = 0
        self.cum_pv = 0.0
        self.cum_vol = 0

    def on_bar(self, b: Bar) -> Signal | None:
        today = b.ts.astimezone(self.c_timezone).date()
        if today != self.day:
            self.__init__(self.c)
            self.day = today
        # Previous completed bars, explicitly excluding the new bar.
        average_vol = fmean(self.volumes) if len(self.volumes) == self.volumes.maxlen else 0
        prev_high = max(self.highs) if len(self.highs) == self.highs.maxlen else None
        prev_low = min(self.lows) if len(self.lows) == self.lows.maxlen else None
        self.seen += 1
        af, asl = 2 / (self.c.ema_fast + 1), 2 / (self.c.ema_slow + 1)
        self.fast = b.close if self.fast is None else af * b.close + (1 - af) * self.fast
        self.slow = b.close if self.slow is None else asl * b.close + (1 - asl) * self.slow
        self.cum_vol += b.volume
        self.cum_pv += b.close * b.volume
        vwap = self.cum_pv / self.cum_vol if self.cum_vol else b.close
        self.volumes.append(b.volume)
        self.highs.append(b.high)
        self.lows.append(b.low)
        if (self.seen < max(self.c.ema_slow, self.c.volume_lookback + 1)
                or average_vol <= 0 or prev_high is None or prev_low is None):
            return None
        ratio = b.volume / average_vol
        if ratio < self.c.volume_multiple:
            return None
        fast, slow = self.fast, self.slow
        strength = abs(fast - slow) / b.close
        if fast > slow and b.close > vwap and b.close > prev_high:
            right = "C"
        elif fast < slow and b.close < vwap and b.close < prev_low:
            right = "P"
        else:
            return None
        bucket = "surge" if ratio >= 3 and strength >= 0.001 else "standard"
        return Signal(b.symbol, right, f"{right}:{bucket}", b.ts, ratio, strength)

    @property
    def c_timezone(self):
        from zoneinfo import ZoneInfo
        return ZoneInfo(self.c.timezone)
