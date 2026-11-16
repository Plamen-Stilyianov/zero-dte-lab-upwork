"""Generate FICTIONAL daily strategy returns. Never use as economic evidence."""
from __future__ import annotations
import csv
from datetime import date, timedelta
from pathlib import Path
from random import Random

rng = Random(909)
path = Path("data/SYNTHETIC_statistical_panel.csv")
path.parent.mkdir(exist_ok=True, parents=True)
start = date(2025, 1, 2)
day = start
n = 0
persist = 0.0
with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["session", "strategy_id", "daily_return"])
    while n < 260:
        if day.weekday() < 5:
            # ALL values are fake; overlapping variants intentionally share shocks.
            persist = 0.76 * persist + rng.gauss(0, 0.008)
            common = persist + rng.gauss(0, 0.004)
            for name, drift, exposure in (("frozen_base", 0.00025, 0.75),
                                          ("two_x_volume", 0.00035, 0.83),
                                          ("delta_075", 0.00048, 0.90),
                                          ("new_ai_rule", -0.00015, 1.04),
                                          ("noisy_variant", 0.0, 1.12)):
                event = 0.0 if rng.random() < 0.2 else drift + common * exposure
                writer.writerow([day.isoformat(), name, f"{event:.9f}"])
            n += 1
        day += timedelta(days=1)
print(f"Created {path} with {n} FICTIONAL sessions across 5 variants")
