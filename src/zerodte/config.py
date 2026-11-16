"""Centralized, validated risk configuration."""
from __future__ import annotations

from dataclasses import dataclass, fields
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    symbols: tuple[str, ...] = ("SPY", "QQQ")
    timezone: str = "America/New_York"
    volume_multiple: float = 2.0
    volume_lookback: int = 20
    breakout_lookback: int = 10
    ema_fast: int = 9
    ema_slow: int = 21
    delta_min: float = 0.75
    delta_max: float = 1.00
    stop_premium: float = 0.40
    breakeven_trigger: float = 0.55
    trail_trigger: float = 0.65
    trail_distance: float = 0.45
    max_spread: float = 0.12
    min_option_volume: int = 10
    max_quote_age_seconds: int = 90
    min_entry_time: str = "09:50"
    last_entry_time: str = "15:00"
    force_exit_time: str = "15:20"
    max_positions: int = 1
    max_contracts: int = 1
    max_trades_per_day: int = 3
    daily_loss_limit_usd: float = 150.0
    equity_usd: float = 25000.0
    max_notional_fraction: float = 0.10
    max_risk_fraction: float = 0.002
    commission_per_contract_per_side: float = 0.65
    entry_slippage: float = 0.02
    exit_slippage: float = 0.02
    entry_delay_bars: int = 1  # integer event/bar delay; NOT milliseconds
    learning_min_trades: int = 30
    learning_min_edge_usd: float = 0.0
    min_minutes_until_exit: int = 20
    allow_model_gate: bool = True
    greek_policy: str = "trusted"  # trusted vendor, or experimental (local/synthetic)
    max_greek_age_seconds: int = 30
    max_greek_quote_skew_seconds: int = 60
    max_delta_disagreement: float = 0.08

    def __post_init__(self) -> None:
        from datetime import time
        floats = (self.volume_multiple, self.delta_min, self.delta_max, self.stop_premium,
                  self.breakeven_trigger, self.trail_trigger, self.trail_distance,
                  self.max_spread, self.daily_loss_limit_usd, self.equity_usd,
                  self.max_notional_fraction, self.max_risk_fraction,
                  self.commission_per_contract_per_side, self.entry_slippage,
                  self.exit_slippage, self.learning_min_edge_usd,
                  self.max_delta_disagreement)
        if not all(math.isfinite(x) for x in floats):
            raise ValueError("Non-finite risk setting rejected")
        if self.max_positions != 1:
            raise ValueError("This prototype supports exactly one simultaneous position")
        if not self.symbols or any(not x.isalpha() for x in self.symbols):
            raise ValueError("Symbols must be nonempty alphabetic tickers")
        if not (self.ema_fast >= 2 and self.ema_slow > self.ema_fast):
            raise ValueError("EMA slow must be greater than EMA fast")
        if self.volume_lookback < 2 or self.breakout_lookback < 2:
            raise ValueError("Lookbacks must be >=2")
        if self.volume_multiple < 1.0 or not (0.5 <= self.delta_min <= self.delta_max <= 1):
            raise ValueError("Invalid volume/delta limits")
        if not (0 < self.stop_premium <= 0.40):
            raise ValueError("Stop cannot exceed requested 40-cent rule")
        if not (self.max_spread > 0 and self.trail_distance > 0):
            raise ValueError("Invalid spread/trailing limit")
        if self.breakeven_trigger <= 0 or self.trail_trigger < self.breakeven_trigger:
            raise ValueError("Invalid trailing triggers")
        if not (1 <= self.max_positions <= 2 and 1 <= self.max_contracts <= 10):
            raise ValueError("Invalid exposure limits")
        if not (1 <= self.entry_delay_bars <= 20):
            raise ValueError("entry_delay_bars must be 1..20 completed frames")
        if self.max_trades_per_day < 1 or self.daily_loss_limit_usd <= 0:
            raise ValueError("Invalid daily risk limits")
        if self.equity_usd <= 0 or not (0 < self.max_notional_fraction <= 0.25):
            raise ValueError("Invalid equity/notional limit")
        if not (0 < self.max_risk_fraction <= 0.02):
            raise ValueError("Invalid fraction at risk")
        if min(self.entry_slippage, self.exit_slippage, self.commission_per_contract_per_side) < 0:
            raise ValueError("Negative execution cost")
        if self.min_option_volume < 0 or self.max_quote_age_seconds <= 0:
            raise ValueError("Invalid option liquidity/quote freshness")
        if not (0 <= self.min_minutes_until_exit <= 60):
            raise ValueError("Invalid expiry buffer")
        if self.greek_policy not in ("trusted", "experimental"):
            raise ValueError("greek_policy must be trusted or experimental")
        if not 0 < self.max_greek_age_seconds <= 120:
            raise ValueError("Greek maximum age must be 1..120 seconds")
        if not 0 <= self.max_greek_quote_skew_seconds <= 120:
            raise ValueError("Invalid Greek/option quote timestamp skew")
        if not 0 <= self.max_delta_disagreement <= 0.25:
            raise ValueError("Invalid maximum delta disagreement")
        if self.learning_min_trades < 10:
            raise ValueError("Learning must wait for a minimum sample")
        clock = [time.fromisoformat(v) for v in (self.min_entry_time, self.last_entry_time, self.force_exit_time)]
        if not (clock[0] < clock[1] < clock[2] <= time.fromisoformat("15:45")):
            raise ValueError("Invalid entry/forced exit schedule")


def load_settings(path: str | Path | None) -> Settings:
    if not path:
        return Settings()
    obj = json.loads(Path(path).read_text(), parse_constant=lambda v: (_ for _ in ()).throw(
        ValueError(f"Non-finite JSON constant prohibited: {v}")))
    valid = {f.name for f in fields(Settings)}
    bad = set(obj) - valid
    if bad:
        raise ValueError(f"Unknown config keys: {sorted(bad)}")
    if "symbols" in obj:
        obj["symbols"] = tuple(obj["symbols"])
    return Settings(**obj)
