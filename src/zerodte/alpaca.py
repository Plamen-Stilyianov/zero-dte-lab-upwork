"""Read-only Alpaca OPRA/SIP data ingestion for local paper simulation.

No trading endpoints, brokerage orders, deposits or live account writes exist in this module.
A production OMS must be separately implemented and reconciled with broker positions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .greeks import estimated_delta
from .models import Bar, OptionQuote, parse_ts

OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
MARKET_DATA = "https://data.alpaca.markets"
PAPER_READ_ONLY = "https://paper-api.alpaca.markets"


class AlpacaDataError(RuntimeError):
    pass


class AlpacaMarketData:
    def __init__(self) -> None:
        self.key = os.environ.get("APCA_API_KEY_ID", "")
        self.secret = os.environ.get("APCA_API_SECRET_KEY", "")
        self.option_feed = os.environ.get("ALPACA_OPTION_FEED", "opra")
        self.stock_feed = os.environ.get("ALPACA_STOCK_FEED", "sip")
        if not self.key or not self.secret:
            raise AlpacaDataError("Alpaca data API credentials required; no market data available")
        if self.option_feed != "opra" or self.stock_feed != "sip":
            raise AlpacaDataError("OPRA and SIP feeds required for this intraday research worker; no delayed substitutes")

    def _get(self, base: str, path: str, query: dict | None = None) -> dict:
        url = base + path
        if query:
            url += "?" + urlencode(query)
        req = Request(url, headers={"APCA-API-KEY-ID": self.key,
                                    "APCA-API-SECRET-KEY": self.secret,
                                    "Accept": "application/json"})
        try:
            with urlopen(req, timeout=12) as reply:  # noqa: S310 - two fixed HTTPS API hosts
                return json.loads(reply.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            # Never leak credentials or raw response in logs.
            raise AlpacaDataError(f"Alpaca read-only request failed: {type(exc).__name__}") from exc

    def clock(self) -> dict:
        return self._get(PAPER_READ_ONLY, "/v2/clock")

    def latest_bar(self, symbol: str) -> tuple[datetime, Bar]:
        payload = self._get(MARKET_DATA, f"/v2/stocks/{quote(symbol)}/bars/latest", {"feed": "sip"})
        b = payload["bar"]
        source_ts = parse_ts(b["t"])
        # Timestamp on latest bar is bar START, not the timestamp of observation.
        bar = Bar(source_ts + timedelta(minutes=1), symbol, float(b["c"]),
                  float(b["h"]), float(b["l"]), int(b["v"]))
        return source_ts, bar

    @staticmethod
    def parse_occ(symbol: str):
        match = OCC.fullmatch(symbol)
        if match is None:
            return None
        root, yymmdd, right, strike = match.groups()
        from datetime import date
        try:
            expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
            return root, expiry, right, int(strike) / 1000
        except ValueError:
            return None

    def _quote(self, occ_symbol: str, snapshot: dict, spot: float,
               volume: int) -> OptionQuote | None:
        occ = self.parse_occ(occ_symbol)
        if occ is None:
            return None
        root, expiry, right, strike = occ
        q = snapshot.get("latestQuote")
        if not isinstance(q, dict):
            return None
        try:
            bid, ask = float(q["bp"]), float(q["ap"])
            quote_ts = parse_ts(q["t"])
            delta = estimated_delta(spot, strike, (bid + ask) / 2, right, quote_ts)
            return OptionQuote(quote_ts, occ_symbol, root, expiry, right, strike,
                               bid, ask, delta, volume, 100,
                               "local_bs_research", quote_ts)
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    def chain(self, symbol: str, spot: float, now: datetime) -> list[OptionQuote]:
        from zoneinfo import ZoneInfo
        day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        params = {"feed": "opra", "expiration_date": day,
                  "strike_price_gte": round(spot * 0.97, 2),
                  "strike_price_lte": round(spot * 1.03, 2), "limit": 1000}
        raw = {}
        for _ in range(5):
            payload = self._get(MARKET_DATA, f"/v1beta1/options/snapshots/{quote(symbol)}", params)
            raw.update(payload.get("snapshots") or {})
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        else:
            # Incomplete option universe is unsafe for ranked contract selection.
            raise AlpacaDataError("Option chain pagination exceeded hard cap")
        quotes = []
        for option_symbol, snapshot in raw.items():
            q = self._quote(option_symbol, snapshot, spot, 0)
            if (q is not None and q.expiry.isoformat() == day
                    and q.is_current(now, 20) and q.delta is not None):
                quotes.append(q)
        candidates = sorted(quotes, key=lambda q: abs(abs(q.delta) - .78))[:25]
        volumes = self.option_volumes([q.symbol for q in candidates], now)
        # No volume observation => 0 => strategy rejects unknown liquidity.
        return [OptionQuote(q.ts, q.symbol, q.underlying, q.expiry,
                            q.right, q.strike, q.bid, q.ask, q.delta,
                            volumes.get(q.symbol, 0), 100,
                            q.greek_provider, q.delta_ts) for q in candidates]

    def option_volumes(self, symbols: list[str], now: datetime) -> dict[str, int]:
        if not symbols:
            return {}
        # Last 20 actual 1-minute option bars, NOT "latest trade size" masquerading as volume.
        payload = self._get(MARKET_DATA, "/v1beta1/options/bars", {
            "symbols": ",".join(symbols), "timeframe": "1Min", "feed": "opra",
            "start": (now - timedelta(minutes=21)).isoformat(),
            "end": (now - timedelta(minutes=1)).isoformat(),
            "limit": 10000,
        })
        if payload.get("next_page_token"):
            raise AlpacaDataError("Option volume bar pagination incomplete")
        return {s: sum(int(b["v"]) for b in bars) for s, bars in (payload.get("bars") or {}).items()}

    def contract(self, symbol: str, spot: float) -> OptionQuote | None:
        data = self._get(MARKET_DATA, "/v1beta1/options/snapshots",
                         {"symbols": symbol, "feed": "opra"})
        return self._quote(symbol, (data.get("snapshots") or {}).get(symbol, {}), spot, 0)
