"""Combine hourly cumulative statistics with fine-grained source states, without overlap."""
from .meter_math import number, integrate


def seconds(value):
    value = float(value)
    return value / 1000 if value > 100_000_000_000 else value


def cumulative_at(rows, points, target, resetting):
    anchors = [r for r in rows if seconds(r['end']) <= target + 0.001
               and number(r.get('sum')) is not None and number(r.get('state')) is not None]
    if not anchors:
        return None
    row = max(anchors, key=lambda r: seconds(r['end']))
    at = seconds(row['end'])
    if abs(at - target) < 0.001:
        return {'value': float(row['sum']), 'sample_at': at, 'complete': True, 'exact': True}
    # No interpolation through old hourly records: bridge only where detailed
    # history actually contains a baseline at the anchor, or a newer sample.
    before = [(ts, value) for ts, value in points if ts <= at and number(value) is not None]
    after = [(ts, value) for ts, value in points if at < ts <= target]
    if not before and not after:
        # Hourly statistics cannot reconstruct minute-level samples that were
        # purged. Hold the preceding recorded hour, explicitly mark approximation.
        if target - at <= 3600:
            return {'value': float(row['sum']), 'sample_at': at, 'complete': True, 'exact': False}
        return None
    if before and abs(float(max(before)[1]) - float(row['state'])) > 0.001:
        return None  # unit/schema disagreement or a missing reset; do not invent a bridge
    if not before and after and min(ts for ts, _ in after) - at > 3600:
        return None
    bridge = integrate([(at, row['state'])] + after, at, target, resetting)
    return {'value': float(row['sum']) + (bridge['kwh'] or 0.0),
            'sample_at': bridge['sample_at'] or at, 'complete': not bridge['uncertain'], 'exact': not bridge['uncertain']}


def consumption(rows, points, start, end, resetting=True, baseline=None):
    if end < start:
        return {'kwh': None, 'complete': False, 'coverage_start': None, 'sample_at': None, 'method': 'outside_period'}
    base = baseline or cumulative_at(rows, points, start, resetting)
    final = cumulative_at(rows, points, end, resetting)
    if base and final:
        value = final['value'] - base['value']
        if value >= -0.000001:
            return {'kwh': round(max(0, value), 6), 'complete': base['complete'] and final['complete'],
                    'coverage_start': start, 'sample_at': final['sample_at'], 'method': 'hourly_statistics+source_history', 'exact': bool(base.get('exact') and final.get('exact'))}
    # A fully retained detailed period remains valid even with no long-term stats.
    detailed = integrate(points, start, end, resetting)
    return {**detailed, 'method': 'source_history_only'}
