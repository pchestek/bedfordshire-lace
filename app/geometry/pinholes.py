"""Pinhole placement — edge-sampling approach.

Pinholes are placed by sampling directly along the Shapely-offset edge
polylines at uniform arc-length intervals.  This guarantees every pinhole
lies exactly on an edge line, even at tight corners where the normal-
projection approach would place pins inside the trail body.

Stagger pattern
---------------
Side A (left edge) is sampled starting at arc-length 0.
Side B (right edge) is sampled starting at arc-length pin_spacing / 2.

Same-side pins are therefore pin_spacing apart; adjacent cross-side pins
are pin_spacing / 2 apart.
"""
import math
import bisect


def trail_edge_pinholes(left_edge, right_edge, pin_spacing_mm):
    """
    Place staggered pinholes along the two edge polylines.

    left_edge, right_edge — lists of (x, y) from offset_polyline().
    pin_spacing_mm        — spacing between same-side consecutive pins.

    Returns list of dicts:
        {'x': float, 'y': float, 'side': 'a'|'b', 'corner': False}
    """
    pins = []

    for pt in _sample_polyline(left_edge, 0.0, pin_spacing_mm):
        pins.append({'x': pt[0], 'y': pt[1], 'side': 'a', 'corner': False})

    for pt in _sample_polyline(right_edge, pin_spacing_mm / 2.0, pin_spacing_mm):
        pins.append({'x': pt[0], 'y': pt[1], 'side': 'b', 'corner': False})

    return pins


def _sample_polyline(points, start_offset, spacing):
    """
    Sample a polyline at uniform arc-length intervals.

    start_offset — arc-length position of the first sample.
    spacing      — distance between consecutive samples.

    Returns list of (x, y) tuples.
    """
    pts = list(points)
    if len(pts) < 2 or spacing <= 0:
        return []

    # Build cumulative arc-length table
    arc = [0.0]
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        arc.append(arc[-1] + math.sqrt(dx * dx + dy * dy))

    total = arc[-1]
    if total <= 0:
        return []

    result = []
    d = start_offset
    while d <= total + 1e-9:
        idx = bisect.bisect_right(arc, d) - 1
        idx = max(0, min(idx, len(arc) - 2))
        d0, d1 = arc[idx], arc[idx + 1]
        frac = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        x = pts[idx][0] + frac * (pts[idx + 1][0] - pts[idx][0])
        y = pts[idx][1] + frac * (pts[idx + 1][1] - pts[idx][1])
        result.append((x, y))
        d += spacing

    return result
