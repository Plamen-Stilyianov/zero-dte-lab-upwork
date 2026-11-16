"""QuantConnect cloud-only, read-only SPY 0DTE data feasibility probe.

Paste into QuantConnect cloud Python project main.py. This OBSERVER NEVER TRADES.
Cloud free tier has minute historical data, not subsecond options history.
Delta is requested from OptionContract.greeks at on_data time, not the daily
OptionFilterUniverse.delta value. These are model outputs, not OPRA truth.

The script is an unexecuted example; requires LEAN cloud APIs/data/entitlement.
"""
from AlgorithmImports import *  # noqa: F403,F401  # provided by LEAN cloud runtime


class FreeCloudZeroDTEObserver(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2026, 10, 5)
        self.set_end_date(2026, 10, 9)
        self.set_cash(25_000)
        self.spy = self.add_equity('SPY', Resolution.MINUTE).symbol
        option = self.add_option('SPY', Resolution.MINUTE)
        option.set_filter(lambda universe: universe.expiration(0, 0).strikes(-20, 20))
        self.option_symbol = option.symbol
        self.day_counts = {}
        self.selected_samples = 0

    def on_data(self, data):
        chain = data.option_chains.get(self.option_symbol)
        if chain is None:
            return
        session = self.time.date().isoformat()
        self.day_counts[session] = self.day_counts.get(session, 0) + 1
        for contract in chain:
            if contract.expiry.date() != self.time.date():
                continue
            if contract.bid_price <= 0 or contract.ask_price <= contract.bid_price:
                continue
            if contract.ask_price - contract.bid_price > .12:
                continue
            # Request per-contract on_data model delta, not a daily universe filter Greek.
            delta = float(contract.greeks.delta)
            if .75 <= abs(delta) <= 1.0 and self.selected_samples < 15:
                self.debug(f'OBSERVE {self.time.isoformat()} {contract.symbol} '
                           f'delta={delta:.4f} bid={contract.bid_price:.2f} '
                           f'ask={contract.ask_price:.2f} (NOT AN ORDER)')
                self.selected_samples += 1

    def on_end_of_algorithm(self):
        for session, count in sorted(self.day_counts.items()):
            self.debug(f'0DTE_RESEARCH_SESSION {session} chain_slices={count}')
        self.debug('OBSERVER COMPLETE. NO ORDERS. NO STRATEGY P&L.')
