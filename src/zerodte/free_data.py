"""Bounded, read-only DoltHub public-data discovery.

No DoltHub row is automatically promoted to an intraday options replay quote.
The public dataset's license, timestamps and chain methodology require auditing.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HOST = 'https://www.dolthub.com'
RESOURCE = '/api/v2/databases/post-no-preference/options/sql'
# Fixed audited queries. We intentionally do not accept arbitrary user SQL.
QUERIES = {
    'tables': 'SHOW TABLES',
    'chain_schema': 'DESCRIBE option_chain',
    'volatility_schema': 'DESCRIBE volatility_history',
    'chain_sample': 'SELECT * FROM option_chain LIMIT 3',
}
MAX_RESPONSE_BYTES = 2_000_000


def parse_query_response(payload: dict, query_name: str) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
        raise ValueError('Malformed DoltHub SQL response')
    result = payload['data']
    if str(result.get('status', '')).casefold() != 'success':
        raise ValueError('DoltHub query did not succeed: ' + str(result.get('message', result.get('status'))))
    rows = result.get('rows')
    columns = result.get('columns')
    if not isinstance(rows, list) or not isinstance(columns, list):
        raise ValueError('DoltHub SQL response lacks rows/columns')
    return {
        'query_name': query_name, 'columns': columns, 'rows': rows,
        'status': 'success', 'data_classification': 'unverified_public_research_data',
        'intraday_execution_eligible': False,
    }


def query_dolthub(query_name: str, *, opener=urlopen) -> dict:
    if query_name not in QUERIES:
        raise ValueError('Only fixed, read-only schema/sample queries are permitted')
    url = HOST + RESOURCE + '?' + urlencode({'ref': 'master', 'q': QUERIES[query_name], 'limit': '10'})
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'ZeroDTE-Lab-research/0.4'})
    with opener(request, timeout=20) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Exceeded bounded public API response size')
        payload = json.loads(raw.decode('utf-8'))
    result = parse_query_response(payload, query_name)
    result['source'] = 'post-no-preference/options'
    result['query'] = QUERIES[query_name]
    return result


def inspect_dolthub(query_name: str, output: str | None = None, *, opener=urlopen) -> dict:
    result = query_dolthub(query_name, opener=opener)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
