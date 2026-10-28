"""Pure energy-history arithmetic. No EVN values are used to seed a local meter."""
import math


def number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def integrate(points, start, end, resetting=True):
    """Consume cumulative readings in [start,end], carrying the preceding baseline.

    Return None when fewer than two usable samples exist. A falling reading on a
    resetting source is ignored, matching native utility_meter behavior.
    Invalid samples never become zero; they make coverage incomplete.
    """
    total = 0.0
    previous = None
    first = None
    last = None
    uncertain = False
    resets = 0
    usable = 0
    for ts, raw in sorted(points, key=lambda p: p[0]):
        if ts > end:
            break
        value = number(raw)
        if value is None:
            if ts >= start:
                uncertain = True
            continue
        if ts <= start:
            previous = value
            first = start
            last = ts
            usable = 1
            continue
        if first is None:
            first = ts
        if previous is not None:
            delta = value - previous
            if delta < 0:
                resets += 1
                if resetting:
                    delta = 0
                    if value > 0:
                        uncertain = True
                else:
                    uncertain = True
                    # Non-resetting meter ignores regressions until the old value returns.
                    last = ts
                    continue
            total += delta
        previous = value
        last = ts
        usable += 1
    return {'kwh': round(total, 6) if usable >= 2 else None,
            'coverage_start': first, 'sample_at': last,
            'complete': first is not None and first <= start and not uncertain,
            'uncertain': uncertain, 'resets': resets}
