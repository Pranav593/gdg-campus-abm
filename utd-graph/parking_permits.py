"""Sourced estimates of physical parking designations, not permit eligibility."""
import json
import math
from pathlib import Path

COLORS = ('green', 'gold', 'orange', 'purple')
PERMIT_FIELDS = [
    'permit_types', *[f'permit_{color}_pct' for color in (*COLORS, 'other')],
    'permit_split_status', 'permit_source_url', 'permit_map_effective_date',
    'permit_source_page', 'permit_source_sha256', 'permit_reviewed_on', 'permit_denominator',
    'permit_estimation_method', 'permit_confidence',
    'permit_designation_confidence', 'permit_notes',
]


def enrich_permits(graph, catalog=None):
    if catalog is None:
        catalog = json.loads(Path(__file__).with_name('parking_permits.json').read_text(encoding='utf-8'))
    source = catalog['source']
    for code, node in graph.nodes(data=True):
        if node.get('category') != 'parking':
            continue
        record = catalog['lots'].get(code, {})
        split, verified = record.get('split_pct'), record.get('verified_types')
        if split is not None:
            if set(split) != set((*COLORS, 'other')):
                raise ValueError(f'Incomplete permit split for {code}')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                   not math.isfinite(v) or not 0 <= v <= 100 for v in split.values()):
                raise ValueError(f'Invalid permit percentage for {code}')
            if not math.isclose(sum(split.values()), 100, abs_tol=.001):
                raise ValueError(f'Permit percentages must total 100 for {code}')
            if not isinstance(verified, list) or len(set(verified)) != len(verified) or not set(verified) <= set(COLORS):
                raise ValueError(f'Invalid mapped permit types for {code}')
            if {c for c in COLORS if split[c] > 0} != set(verified):
                raise ValueError(f'Estimated colors differ from mapped designations for {code}')
        elif verified is not None:
            raise ValueError(f'Unknown split must not assert mapped types for {code}')
        node['permit_split_pct'] = dict(split) if split is not None else None
        node['permit_types'] = list(verified) if verified is not None else None
        for color in (*COLORS, 'other'):
            node[f'permit_{color}_pct'] = split[color] if split is not None else None
        node.update(
            permit_split_status='estimated' if split is not None else 'unknown',
            permit_source_url=source['url'], permit_map_effective_date=source['effective_date'],
            permit_source_sha256=source['sha256'], permit_source_page=record.get('source_page'),
            permit_reviewed_on=source['reviewed_on'], permit_denominator=source['denominator'],
            permit_estimation_method=source['method'],
            permit_confidence=source['confidence'] if split is not None else 'unknown',
            permit_designation_confidence=record.get('designation_confidence', 'unknown'),
            permit_notes=record.get('notes', 'No reviewed official-map record for this parking area.'),
        )
    graph.graph['parking_permit_source'] = dict(source)


def csv_place(row):
    """Keep the graph's list structured while making CSV types interoperable."""
    result = dict(row)
    if 'permit_types' in result and result['permit_types'] is not None:
        result['permit_types'] = json.dumps(result['permit_types'], separators=(',', ':'))
    return result
