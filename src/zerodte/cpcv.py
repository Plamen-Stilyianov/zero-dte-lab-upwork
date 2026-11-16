"""Research-only combinatorial purged cross-validation split *planner*.

CPCV can train on samples chronologically AFTER a test fold. It is not a
forward-only live simulation. Labels MUST cover the full outcome-information
interval [start, end], not just the entry timestamp. Refit any preprocessing
and models within each split; this module only generates leak-checked indices.

Path assignments are provided for the common N-even, k=2 configuration, where
round-robin one-factorization covers each fold exactly once per path. No path
return stitching or model fitting is performed here.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path


@dataclass(frozen=True)
class Observation:
    sample_id: str
    start: datetime
    end: datetime


def _parse_instant(value: str) -> datetime:
    value = value.strip()
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('Intraday timestamps must carry a UTC offset (or Z)')
    return dt.astimezone(timezone.utc)


def load_label_events(source: str | Path) -> tuple[list[Observation], str]:
    path = Path(source)
    data = path.read_bytes()
    observations: list[Observation] = []
    seen: set[str] = set()
    last: datetime | None = None
    with path.open(newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not {'sample_id', 'start', 'end'} <= set(reader.fieldnames):
            raise ValueError('Expected sample_id,start,end CSV columns')
        for row in reader:
            sample = (row.get('sample_id') or '').strip()
            if not sample or sample in seen:
                raise ValueError(f'Empty or repeated sample_id: {sample}')
            start = _parse_instant(row['start'])
            end = _parse_instant(row['end'])
            if end < start:
                raise ValueError(f'End precedes start: {sample}')
            if last is not None and start < last:
                raise ValueError('Event starts must be chronological, not sorted into place')
            observations.append(Observation(sample, start, end))
            seen.add(sample)
            last = start
    if not observations:
        raise ValueError('No observations supplied')
    return observations, hashlib.sha256(data).hexdigest()


def _merge_intervals(indices: list[int], observations: list[Observation]):
    merged: list[tuple[datetime, datetime]] = []
    for idx in indices:
        item = observations[idx]
        if merged and item.start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], item.end))
        else:
            merged.append((item.start, item.end))
    return merged


def _round_robin_paths(n_folds: int, lookup: dict[tuple[int, ...], int]) -> list[dict]:
    players = list(range(n_folds))
    result = []
    for path_id in range(n_folds - 1):
        pairs = [tuple(sorted((players[j], players[n_folds - 1 - j])))
                 for j in range(n_folds // 2)]
        result.append({'path_id': path_id,
                       'fold_to_split': {str(fold): lookup[pair]
                                         for pair in pairs for fold in pair}})
        # Circle method: keep the first element fixed, rotate everyone else.
        players = [players[0], players[-1], *players[1:-1]]
    return result


def build_cpcv(observations: list[Observation], n_folds: int = 6,
               n_test_folds: int = 2, embargo_observations: int = 1,
               max_splits: int = 10000, *, sha256: str | None = None) -> dict:
    n = len(observations)
    if not 3 <= n_folds <= n or n_test_folds < 1 or n_test_folds >= n_folds:
        raise ValueError('Require 3 <= folds <= observations and 1 <= test_folds < folds')
    if embargo_observations < 0 or max_splits < 1:
        raise ValueError('Invalid embargo or max_splits')
    if math.comb(n_folds, n_test_folds) > max_splits:
        raise ValueError('Too many combinations; reduce folds or increase explicit max_splits')
    if any(o.end < o.start for o in observations):
        raise ValueError('Invalid label interval')
    if any(observations[i].start < observations[i - 1].start for i in range(1, n)):
        raise ValueError('Observations must be in chronological order')
    # First folds are equal-sized; remainder goes into later folds.
    q, r = divmod(n, n_folds)
    sizes = [q + (1 if i >= n_folds - r else 0) for i in range(n_folds)]
    folds: list[list[int]] = []
    position = 0
    for size in sizes:
        folds.append(list(range(position, position + size)))
        position += size
    output_splits = []
    lookup: dict[tuple[int, ...], int] = {}
    for fold_combo in itertools.combinations(range(n_folds), n_test_folds):
        test_idx = sorted(i for fold_id in fold_combo for i in folds[fold_id])
        test_set = set(test_idx)
        prohibited = set(test_idx)
        for fold_id in fold_combo:
            # Embargo from the test fold boundary *and* the final test outcome
            # availability time; the latter may be later for multibar labels.
            last = folds[fold_id][-1]
            prohibited.update(range(last + 1, min(n, last + 1 + embargo_observations)))
            final_label_end = max(observations[i].end for i in folds[fold_id])
            after_horizon = next((i for i in range(last + 1, n)
                                  if observations[i].start > final_label_end), n)
            prohibited.update(range(after_horizon, min(n, after_horizon + embargo_observations)))
        merged = _merge_intervals(test_idx, observations)
        starts = [x[0] for x in merged]
        purged = []
        retained = []
        for i, obs in enumerate(observations):
            if i in prohibited:
                continue
            # Test intervals are sorted and unioned; any intersection leaks.
            j = bisect_right(starts, obs.end) - 1
            if j >= 0 and obs.start <= merged[j][1]:
                purged.append(i)
            else:
                retained.append(i)
        emb = sorted(prohibited - test_set)
        if not retained:
            raise ValueError(f'No train observations after purge/embargo for folds {fold_combo}; revise fold counts')
        split_id = len(output_splits)
        lookup[fold_combo] = split_id
        output_splits.append({'split_id': split_id, 'test_folds': list(fold_combo),
                              'train_indices': retained, 'test_indices': test_idx,
                              'purged_indices': purged, 'embargoed_indices': emb,
                              'training_is_forward_only': False})
    # Even-fold pairwise CPCV can be recombined into N-1 complete diagnostic paths.
    paths = (_round_robin_paths(n_folds, lookup)
             if n_test_folds == 2 and n_folds % 2 == 0 else [])
    return {'method': 'combinatorial_purged_cross_validation_split_plan',
            'sample_count': n, 'sample_ids': [o.sample_id for o in observations],
            'source_sha256': sha256, 'n_folds': n_folds, 'n_test_folds': n_test_folds,
            'embargo_observations': embargo_observations,
            'split_count': len(output_splits), 'paths': paths, 'splits': output_splits,
            'limitations': [
                'No model training, features, target construction or returns are calculated.',
                'Train indices can include data from AFTER test indices: CPCV is not a live-forward test.',
                'Label end must cover the entire time interval over which each outcome depends.',
                'Preprocessing, feature selection, and normalization must be refit inside each train split.',
                'Precomputed cross-validation predictions must not be compounded twice when reconstructing paths.',
                'Repeated CPCV folds and reconstructed paths are statistically dependent.',
                'A separately frozen chronological holdout and paper execution remain mandatory.'
            ], 'can_promote_to_live': False}


def cpcv_csv(source: str | Path, out: str | Path, **kwargs) -> dict:
    observations, sha256 = load_label_events(source)
    report = build_cpcv(observations, sha256=sha256, **kwargs)
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
