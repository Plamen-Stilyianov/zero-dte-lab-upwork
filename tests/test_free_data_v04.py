from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from zerodte.free_data import QUERIES, inspect_dolthub, parse_query_response, query_dolthub
from zerodte.greeks_lab import _compute_row, enrich_research_csv, european_bs, solve_iv


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, n):
        return self.content[:n]


def fixture_query(req, timeout):
    assert timeout == 20
    url = urlsplit(req.full_url)
    assert url.netloc == 'www.dolthub.com' and url.scheme == 'https'
    query = parse_qs(url.query)
    assert query['q'] == ['DESCRIBE option_chain']
    assert query['ref'] == ['master']
    data = {'data': {'columns': [{'name': 'Field'}], 'rows': [['ticker']], 'status': 'success'}}
    return FakeResponse(json.dumps(data).encode('utf-8'))


def test_dolthub_fixed_queries_and_unverified_status(tmp_path):
    out = tmp_path / 'probe.json'
    result = inspect_dolthub('chain_schema', str(out), opener=fixture_query)
    assert result['intraday_execution_eligible'] is False
    assert json.loads(out.read_text())['rows'] == [['ticker']]
    with pytest.raises(ValueError, match='Only fixed'):
        query_dolthub('DELETE FROM option_chain', opener=fixture_query)
    assert 'chain_sample' in QUERIES


def test_dolthub_checks_status_and_response_shape():
    with pytest.raises(ValueError, match='did not succeed'):
        parse_query_response({'data': {'status': 'timeout'}}, 'chain_schema')
    with pytest.raises(ValueError, match='Malformed'):
        parse_query_response({'unknown': []}, 'chain_schema')


def test_bs_known_call_and_put():
    call = european_bs(100, 100, 1, .2, 'C', 0, 0)
    put = european_bs(100, 100, 1, .2, 'P', 0, 0)
    assert call.price == pytest.approx(7.965567, abs=1e-5)
    assert call.delta == pytest.approx(.5398278, abs=1e-6)
    assert put.price == pytest.approx(call.price, abs=1e-10)
    assert call.delta - put.delta == pytest.approx(1.0, abs=1e-10)
    assert call.gamma == pytest.approx(.0198476, abs=1e-6)
    assert call.theta_per_calendar_day < 0
    assert call.vega_per_vol_point > 0


def test_iv_inverts_midpoint_and_no_solution():
    model = european_bs(650, 648, .01, .23, 'P', .04, .012)
    iv = solve_iv(model.price, 650, 648, .01, 'P', .04, .012)
    assert iv == pytest.approx(.23, abs=1e-6)
    assert solve_iv(0, 650, 648, .01, 'P', .04, .012) is None
    assert solve_iv(999, 650, 648, .01, 'P', .04, .012) is None


def make_row():
    quote_ts = '2026-11-06T14:30:00+00:00'
    return {'quote_ts': quote_ts, 'spot_ts': '2026-11-06T14:29:59+00:00',
            'decision_ts': '2026-11-06T14:30:01+00:00',
            'expiry_ts': '2026-11-06T21:00:00+00:00',
            'option_symbol': 'SPY261106C00650000', 'right': 'C',
            'spot': '650', 'strike': '650', 'bid': '2.00', 'ask': '2.10',
            'rate': '0.04', 'rate_observed_at': '2026-11-05T21:00:00+00:00',
            'dividend_yield': '0.012'}


def test_enrichment_is_explicitly_research_only(tmp_path):
    data = tmp_path / 'raw.csv'
    out = tmp_path / 'enriched.csv'
    with data.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=make_row())
        writer.writeheader()
        writer.writerow(make_row())
    report = enrich_research_csv(str(data), str(out))
    assert report['enriched_rows'] == 1
    rows = list(csv.DictReader(out.open()))
    assert rows[0]['greek_provider'] == 'local_bs_research'
    assert rows[0]['data_classification'] == 'RESEARCH_ONLY_NOT_EXECUTION_VERIFIED'
    assert .4 <= float(rows[0]['delta']) <= .7


@pytest.mark.parametrize('column,bad_value', [
    ('spot_ts', '2026-11-06T14:30:02+00:00'),
    ('rate_observed_at', '2026-11-06T14:30:02+00:00'),
    ('quote_ts', '2026-11-06T14:31:00+00:00'),
    ('bid', '2.50'),
    ('expiry_ts', '2026-11-07T21:00:00+00:00'),
])
def test_bad_asof_and_bad_quotes_rejected(column, bad_value):
    row = make_row()
    row[column] = bad_value
    with pytest.raises(ValueError):
        _compute_row(row)


def test_too_old_quote_rejected():
    row = make_row()
    row['decision_ts'] = '2026-11-06T14:40:00+00:00'
    with pytest.raises(ValueError, match='stale'):
        _compute_row(row)


def test_existing_local_estimate_does_not_use_future_bar_close(tmp_path):
    from zerodte.data import read_frames
    tape = tmp_path / 'tape.csv'
    row = dict(ts='2026-11-06T14:31:00+00:00', underlying='SPY', close='650',
               high='650.10', low='649.9', volume='12000',
               option_symbol='SPY261106C00650000', expiry='2026-11-06', right='C',
               strike='650', bid='2.0', ask='2.1', option_volume='150',
               quote_ts='2026-11-06T14:30:00+00:00')
    with tape.open('w', newline='') as out:
        w = csv.DictWriter(out, fieldnames=row)
        w.writeheader()
        w.writerow(row)
    frames = list(read_frames(str(tape), 'estimated'))
    assert frames[0].quotes[0].delta is None
