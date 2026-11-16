"""Single-account simulation engine, next-frame entries and bid/ask/slippage fills."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from math import floor
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from .config import Settings
from .learn import regime_permitted
from .greeks_quality import delta_quality_reason
from .models import Frame, OptionQuote, Position, Signal, Trade
from .signal import TrendSignal


class StrategyEngine:
    def __init__(self, config: Settings):
        self.c = config
        self.local_zone = ZoneInfo(config.timezone)
        self.trends = {s: TrendSignal(config) for s in config.symbols}
        self.pending: dict[str, Signal] = {}
        self.pending_bars_remaining: dict[str, int] = {}
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.events: list[str] = []
        self.daily_realized: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        self.last_entry_reject_reason: str | None = None
        self.daily_counts: dict[str, int] = defaultdict(int)
        self.last_ts: dict[str, datetime] = {}
        self.last_day: dict[str, str] = {}
        self.incomplete = False
        self.fixed_regime_allowlist: dict[str, bool] | None = None

    def _clock(self, ts: datetime) -> time:
        return ts.astimezone(self.local_zone).time().replace(tzinfo=None)

    def _local_day(self, ts: datetime) -> str:
        return ts.astimezone(self.local_zone).date().isoformat()

    def _current_quote(self, frame: Frame, symbol: str) -> OptionQuote | None:
        for q in frame.quotes:
            if q.symbol == symbol and q.is_current(frame.bar.ts, self.c.max_quote_age_seconds):
                return q
        return None

    def _exit(self, q: OptionQuote, ts: datetime, reason: str) -> Trade:
        p = self.position
        if p is None:
            raise RuntimeError("No position")
        fill = max(0.01, q.bid - self.c.exit_slippage)
        pnl_amount = ((Decimal(str(fill)) - Decimal(str(p.entry_price))) * Decimal("100")
                      - 2 * Decimal(str(self.c.commission_per_contract_per_side))) * p.qty
        pnl = float(pnl_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        trade = Trade(p.option, p.underlying, p.right, p.regime,
                      p.entry_time, ts, p.entry_price, fill, p.qty, pnl,
                      reason, p.entry_delta, p.entry_volume_ratio)
        self.trades.append(trade)
        self.daily_realized[self._local_day(ts)] += Decimal(str(pnl))
        self.events.append(f"{ts.isoformat()} EXIT {p.option} {reason} pnl={pnl:+.2f}")
        self.position = None
        return trade

    def _handle_position(self, frame: Frame) -> None:
        p = self.position
        if p is None or frame.bar.symbol != p.underlying:
            return
        q = self._current_quote(frame, p.option)
        if q is None:
            if self._clock(frame.bar.ts) >= time.fromisoformat(self.c.force_exit_time):
                self.incomplete = True
                self.events.append(f"{frame.bar.ts.isoformat()} NO VALID QUOTE FOR FORCE EXIT")
            return
        if q.bid <= p.current_stop:
            self._exit(q, frame.bar.ts, "stop_or_trailing")
            return
        if self._clock(frame.bar.ts) >= time.fromisoformat(self.c.force_exit_time):
            self._exit(q, frame.bar.ts, "forced_intraday_exit")
            return
        p.max_bid = max(p.max_bid, q.bid)
        # Trailing stop only ratchets up, never widens.
        if p.max_bid >= p.entry_price + self.c.breakeven_trigger:
            p.current_stop = max(p.current_stop, p.entry_price + 0.01)
        if p.max_bid >= p.entry_price + self.c.trail_trigger:
            p.current_stop = max(p.current_stop, p.max_bid - self.c.trail_distance)

    def _eligible(self, q: OptionQuote, signal: Signal, now: datetime) -> bool:
        local_now = now.astimezone(self.local_zone)
        if q.underlying != signal.underlying or q.right != signal.right:
            return False
        if q.expiry != local_now.date() or q.multiplier != 100:
            return False
        if not q.is_current(now, self.c.max_quote_age_seconds):
            return False
        if delta_quality_reason(q, now, self.c) is not None:
            return False
        if q.delta is None or not (self.c.delta_min <= abs(q.delta) <= self.c.delta_max):
            return False
        if (q.right == "C" and q.delta <= 0) or (q.right == "P" and q.delta >= 0):
            return False
        if q.volume < self.c.min_option_volume or q.ask - q.bid > self.c.max_spread:
            return False
        return True

    def _entry(self, frame: Frame, signal: Signal) -> bool:
        self.last_entry_reject_reason = None

        def veto(reason: str) -> bool:
            self.last_entry_reject_reason = reason
            return False

        ts = frame.bar.ts
        clock = self._clock(ts)
        day = self._local_day(ts)
        if not (time.fromisoformat(self.c.min_entry_time) <= clock
                <= time.fromisoformat(self.c.last_entry_time)):
            return veto("outside_entry_window")
        if datetime.combine(ts.astimezone(self.local_zone).date(), time(16),
                            tzinfo=self.local_zone).astimezone(ts.tzinfo) - ts < timedelta(minutes=self.c.min_minutes_until_exit):
            return veto("expiry_exit_buffer")
        if self.position:
            return veto("position_already_open")
        if self.daily_counts[day] >= self.c.max_trades_per_day:
            return veto("daily_trade_count_limit")
        if self.daily_realized[day] <= -Decimal(str(self.c.daily_loss_limit_usd)):
            return veto("daily_realized_loss_limit")
        if self.fixed_regime_allowlist is not None:
            if not self.fixed_regime_allowlist.get(signal.regime, False):
                return veto("frozen_regime_model_veto")
        elif self.c.allow_model_gate and not regime_permitted(signal.regime, self.trades,
                    ts.astimezone(self.local_zone).date(), self.c.learning_min_trades,
                    self.c.learning_min_edge_usd):
            return veto("prior_trades_model_veto")
        matches = [q for q in frame.quotes if self._eligible(q, signal, ts)]
        # Deep enough in the money to meet threshold, but as close to 0.75 as possible.
        matches.sort(key=lambda q: (abs(abs(q.delta) - self.c.delta_min),
                                    q.ask - q.bid, q.symbol))
        if not matches:
            return veto("no_eligible_contract_or_greek")
        q = matches[0]
        entry = round(q.ask + self.c.entry_slippage, 4)
        per_contract_risk = (Decimal("100") *
                             (Decimal(str(self.c.stop_premium)) + Decimal(str(self.c.entry_slippage))
                              + Decimal(str(self.c.exit_slippage)))
                             + 2 * Decimal(str(self.c.commission_per_contract_per_side)))
        max_risk_usd = min(Decimal(str(self.c.equity_usd)) * Decimal(str(self.c.max_risk_fraction)),
                           Decimal(str(self.c.daily_loss_limit_usd)) + self.daily_realized[day])
        max_notional_usd = Decimal(str(self.c.equity_usd)) * Decimal(str(self.c.max_notional_fraction))
        qty = min(self.c.max_contracts, int(max_risk_usd // per_contract_risk),
                  int(max_notional_usd // (Decimal(str(entry)) * 100)))
        if qty < 1:
            return veto("insufficient_risk_or_notional_budget")
        self.position = Position(q.symbol, q.underlying, q.right, signal.regime,
                                 ts, entry, qty, max(0.01, entry - self.c.stop_premium),
                                 q.bid, signal.volume_ratio, q.delta)
        self.daily_counts[day] += 1
        self.events.append(f"{ts.isoformat()} ENTRY {q.symbol} {signal.regime} qty={qty} ask={entry:.2f}")
        return True

    def on_frame(self, frame: Frame) -> None:
        b = frame.bar
        if b.symbol not in self.trends:
            return
        day = self._local_day(b.ts)
        if b.symbol in self.last_ts and b.ts <= self.last_ts[b.symbol]:
            raise ValueError("Each symbol must have strictly increasing timestamps")
        self.last_ts[b.symbol] = b.ts
        if self.last_day.get(b.symbol) != day:
            self.pending.pop(b.symbol, None)
            self.pending_bars_remaining.pop(b.symbol, None)
            self.last_day[b.symbol] = day
        self._handle_position(frame)
        # Deliberately enter on NEXT frame after detecting a completed bar signal.
        pending = self.pending.get(b.symbol)
        if pending is not None:
            remaining = self.pending_bars_remaining.get(b.symbol, 1)
            if remaining <= 1:
                self.pending.pop(b.symbol, None)
                self.pending_bars_remaining.pop(b.symbol, None)
                if self._local_day(pending.observed_at) == day:
                    self._entry(frame, pending)
            else:
                self.pending_bars_remaining[b.symbol] = remaining - 1
        next_signal = self.trends[b.symbol].on_bar(b)
        if next_signal is not None and b.symbol not in self.pending:
            self.pending[b.symbol] = next_signal
            self.pending_bars_remaining[b.symbol] = self.c.entry_delay_bars

    def finalize(self) -> None:
        if self.position is not None:
            self.incomplete = True
            self.events.append("UNCLOSED POSITION: historical tape incomplete; results NOT validated")
