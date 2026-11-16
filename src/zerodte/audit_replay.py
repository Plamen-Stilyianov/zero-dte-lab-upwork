"""Evidence trail of research trades, signals and skipped trade intents.

No LLM or order API has access to the ledger; only serializes decisions observed
in an event-driven replay. 'Rejected' reasons are coarse until detailed risk
reason codes are instrumented in the engine.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from .audit_ledger import DecisionLedger, digest, verify_ledger
from .config import Settings
from .data import read_frames
from .engine import StrategyEngine
from .models import Frame
from .report import make_report


def trace_replay(data: str, config: Settings, ledger: str, out: str,
                 delta_source: str = "provided") -> dict:
    engine = StrategyEngine(config)
    config_hash = digest(asdict(config))
    count = 0
    with DecisionLedger(ledger) as journal:
        journal.append("research_replay_begin", {
            "strategy_config_sha256": config_hash,
            "input_path_as_supplied": str(data),
            "delta_source_mode": delta_source,
            "research_only": True,
        })
        for frame in read_frames(data, delta_source):
            symbol = frame.bar.symbol
            before_position = engine.position
            before_signal = engine.pending.get(symbol)
            old_trade_count = len(engine.trades)
            engine.on_frame(frame)
            after_position = engine.position
            current_signal = engine.pending.get(symbol)
            at = frame.bar.ts.isoformat()
            if before_signal is not None and current_signal is not before_signal:
                if before_position is None and after_position is None and len(engine.trades) == old_trade_count:
                    journal.append("signal_not_executed", {
                        "observed_at": before_signal.observed_at.isoformat(), "evaluated_at": at,
                        "underlying": symbol, "reason": "eligibility_or_risk_gate",
                        "reason_detail_unavailable": True})
            if current_signal is not None and current_signal is not before_signal:
                journal.append("signal_created", {"observed_at": at, "underlying": symbol,
                    "right": current_signal.right, "regime": current_signal.regime,
                    "volume_ratio": current_signal.volume_ratio})
            if before_position is None and after_position is not None:
                q = next((q for q in frame.quotes if q.symbol == after_position.option), None)
                journal.append("virtual_entry", {"observed_at": at, "option": after_position.option,
                    "qty": after_position.qty, "entry_price": after_position.entry_price,
                    "delta": after_position.entry_delta, "greek_provider": q.greek_provider if q else None,
                    "quote_timestamp": q.ts.isoformat() if q else None,
                    "source_delta_timestamp": q.delta_ts.isoformat() if q and q.delta_ts else None})
            for t in engine.trades[old_trade_count:]:
                journal.append("virtual_exit", t.as_dict())
            count += 1
        engine.finalize()
        journal.append("research_replay_end", {"frames": count, "trades": len(engine.trades),
            "incomplete": engine.incomplete})
    check = verify_ledger(ledger)
    result = {"frames": count, "trades": len(engine.trades), "ledger": str(ledger),
              "ledger_status": check, "config_sha256": config_hash,
              "summary": make_report(engine, out, label="audited_replay")}
    (Path(out) / "audit_replay.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
