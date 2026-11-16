"""Point-in-time delta provenance and optional independent cross-checks.

A Greek is a pricing-model output, NOT a trade/exchange observation. Never
manufacture an 'authoritative' delta when its source timestamp is unknown.
"""
from __future__ import annotations

from datetime import datetime

from .config import Settings
from .models import OptionQuote

# Allow vendor labels, NOT an assertion that a vendor's methodology is infallible.
VENDORS = frozenset({"thetadata", "orats", "cboe", "cboe_datashop", "broker_vendor"})
RESEARCH_ONLY = frozenset({"synthetic", "local_bs_research", "nautilus_local"})


def delta_quality_reason(q: OptionQuote, observed_at: datetime, c: Settings) -> str | None:
    """Return a fail-closed rejection reason, or None if this *filter* passes.

    Neither a pass nor vendor brand implies the Greek is correct or marketable.
    A matching independent reference is optional; absence is never called verified.
    """
    if q.delta is None:
        return "missing_delta"
    if q.greek_provider is None or q.delta_ts is None:
        return "unknown_provenance_or_timestamp"
    name = q.greek_provider.casefold().strip()
    if c.greek_policy == "trusted" and name not in VENDORS:
        return "untrusted_greek_source"
    if name not in VENDORS | RESEARCH_ONLY:
        return "unrecognized_greek_source"
    time_age = (observed_at - q.delta_ts).total_seconds()
    if not 0 <= time_age <= c.max_greek_age_seconds:
        return "future_or_stale_delta"
    skew = abs((q.ts - q.delta_ts).total_seconds())
    if skew > c.max_greek_quote_skew_seconds:
        return "misaligned_greek_and_quote"
    if q.reference_delta is not None:
        if not q.reference_provider:
            return "missing_reference_provider"
        if q.reference_provider.casefold().strip() == name:
            return "reference_not_independent"
        if q.reference_provider.casefold().strip() not in VENDORS | RESEARCH_ONLY:
            return "unrecognized_reference_provider"
        if q.reference_delta_ts is None:
            return "missing_reference_timestamp"
        age = (observed_at - q.reference_delta_ts).total_seconds()
        if not 0 <= age <= c.max_greek_age_seconds:
            return "future_or_stale_reference_delta"
        if abs(q.delta - q.reference_delta) > c.max_delta_disagreement:
            return "conflicting_delta_sources"
        if q.right == "C" and q.reference_delta <= 0:
            return "wrong_reference_delta_sign"
        if q.right == "P" and q.reference_delta >= 0:
            return "wrong_reference_delta_sign"
    return None
