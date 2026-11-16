"""v0.6 deterministic split/no-leakage and studentized stepdown regression tests."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from zerodte.cpcv import Observation, build_cpcv, load_label_events
from zerodte.romano_wolf import romano_wolf_panel
from zerodte.statistical_audit import ReturnPanel


def labels(n=24, length=0):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Observation(str(i), base + timedelta(days=i), base + timedelta(days=i + length))
            for i in range(n)]


def panel(n=160, positive=0.0006, seed=42):
    from datetime import date
    rng = Random(seed)
    base = date(2026, 1, 1)
    values = []
    for _ in range(n):
        shock = rng.gauss(0, 0.004)
        values.append((positive + shock, positive + 0.9*shock + rng.gauss(0, 0.0008),
                       rng.gauss(0, 0.004)))
    days = tuple(base + timedelta(days=i) for i in range(n))
    return ReturnPanel(days, ('one', 'two', 'noise'), tuple(values), 'synthetic-sha')


def test_cpcv_split_count_disjoint_and_coverage():
    p = build_cpcv(labels(), n_folds=6, n_test_folds=2, embargo_observations=2)
    assert p['split_count'] == 15
    for split in p['splits']:
        tr, te, pur, emb = (set(split[k]) for k in
                             ('train_indices','test_indices','purged_indices','embargoed_indices'))
        assert len(te) == 8
        assert not tr & te and not tr & pur and not tr & emb
        assert len(tr | te | pur | emb) == 24
    assert p['can_promote_to_live'] is False


def test_cpcv_purge_uses_full_label_interval_not_just_sample_start():
    observed = labels(18)
    # Sample 0 reveals an outcome only several periods later, overlapping test fold 1.
    observed[0] = Observation('0', observed[0].start, observed[8].start)
    plan = build_cpcv(observed, n_folds=6, n_test_folds=2, embargo_observations=0)
    split = next(s for s in plan['splits'] if s['test_folds'] == [1, 3])
    assert 0 in split['purged_indices']
    assert 0 not in split['train_indices']
    for s in plan['splits']:
        for i in s['train_indices']:
            for j in s['test_indices']:
                assert observed[i].end < observed[j].start or observed[i].start > observed[j].end


def test_cpcv_embargo_also_removes_after_noncontiguous_test_blocks():
    plan = build_cpcv(labels(), n_folds=6, n_test_folds=2, embargo_observations=2)
    split = next(s for s in plan['splits'] if s['test_folds'] == [1, 3])
    assert {8, 9, 16, 17}.issubset(split['embargoed_indices'])


def test_cpcv_round_robin_diagnostic_paths():
    plan = build_cpcv(labels(24), n_folds=6, n_test_folds=2)
    assert len(plan['paths']) == 5
    uses = Counter()
    for path in plan['paths']:
        assert set(map(int, path['fold_to_split'])) == set(range(6))
        for fold, split in path['fold_to_split'].items():
            assert int(fold) in plan['splits'][split]['test_folds']
            uses[(split, int(fold))] += 1
    for split in plan['splits']:
        assert all(uses[(split['split_id'], fold)] == 1 for fold in split['test_folds'])


def test_cpcv_odd_or_three_test_folds_no_unsupported_paths():
    plan = build_cpcv(labels(25), n_folds=5, n_test_folds=2)
    assert plan['split_count'] == 10 and plan['paths'] == []
    plan2 = build_cpcv(labels(24), n_folds=6, n_test_folds=3)
    assert plan2['split_count'] == 20 and plan2['paths'] == []


def test_cpcv_rejects_bad_input(tmp_path):
    path = tmp_path/'labels.csv'
    path.write_text('sample_id,start,end\na,2026-01-01T10:00:00,2026-01-01T11:00:00\n')
    with pytest.raises(ValueError, match='UTC offset'):
        load_label_events(path)
    path.write_text('sample_id,start,end\na,2026-01-02,2026-01-01\n')
    with pytest.raises(ValueError, match='precedes'):
        load_label_events(path)


def test_rw_stepdown_monotonic_and_conservative_vs_raw():
    r = romano_wolf_panel(panel(), iterations=299, seed=13, min_sessions=120)
    h = r['hypotheses']
    ordered = sorted(h, key=lambda v: -v['observed_t'])
    assert [x['romano_wolf_stepdown_p'] for x in ordered] == sorted(
        x['romano_wolf_stepdown_p'] for x in ordered)
    for x in h:
        assert x['romano_wolf_stepdown_p'] + 1e-8 >= x['unadjusted_bootstrap_p']
        assert x['romano_wolf_stepdown_p'] <= x['single_step_max_t_p'] + 1e-8
    assert r['entire_declared_family_supplied']
    assert not r['can_promote_to_live']


def test_rw_reproducible_and_detects_strong_signal():
    p = panel(160, positive=0.003)
    a = romano_wolf_panel(p, iterations=299, seed=2026)
    b = romano_wolf_panel(p, iterations=299, seed=2026)
    assert a == b
    assert a['hypotheses'][0]['pass_rw_alpha']
    assert a['hypotheses'][2]['romano_wolf_stepdown_p'] > 0.01


def test_rw_missing_trials_blocks_full_family_inference():
    r = romano_wolf_panel(panel(), iterations=199, declared_trials=40)
    assert not r['entire_declared_family_supplied']
    assert not any(row['pass_rw_alpha'] for row in r['hypotheses'])


def test_rw_constant_positive_strategy_fails_closed():
    p = panel()
    p = ReturnPanel(p.dates, ('constant',), tuple((0.01,) for _ in p.dates), 'x')
    with pytest.raises(ValueError, match='degenerate'):
        romano_wolf_panel(p, iterations=199)


def test_rw_invalid_parameters_rejected():
    with pytest.raises(ValueError, match='iterations'):
        romano_wolf_panel(panel(), iterations=100)
    with pytest.raises(ValueError, match='declared_trials'):
        romano_wolf_panel(panel(), iterations=199, declared_trials=2)


def test_cpcv_randomized_interval_oracle():
    rng = Random(361)
    for _ in range(25):
        spans = [rng.randrange(0, 4) for _ in range(40)]
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        observations = [Observation(str(i), base + timedelta(days=i),
                                    base + timedelta(days=i+spans[i])) for i in range(40)]
        result = build_cpcv(observations, n_folds=5, n_test_folds=2,
                            embargo_observations=2)
        for split in result['splits']:
            assert not (set(split['train_indices']) & set(split['test_indices']))
            for i in split['train_indices']:
                assert all(not (observations[i].start <= observations[j].end and
                                observations[i].end >= observations[j].start)
                           for j in split['test_indices'])


def test_cpcv_refuses_oversized_label_horizons():
    obs = labels(18, length=100)
    with pytest.raises(ValueError, match='No train observations'):
        build_cpcv(obs, n_folds=6, n_test_folds=2)
