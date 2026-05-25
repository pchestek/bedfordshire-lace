"""Trail crossing detection.

Finds points where trail centerlines intersect — both between two different
trails and within a single self-crossing trail (figure-8).  Each intersection
becomes a Crossing element (placed by canvas), with four pinholes at the
inside corners of the trail-edge overlap.
"""
import math
from collections import Counter

from shapely.geometry import LineString, Point, MultiPoint
from shapely.ops import unary_union


def find_centerline_intersections(trails):
    """Return all centerline intersection points (pair + self).

    trails — list of Trail objects with `.centerline` populated.

    Returns list of dicts:
        {'i': trail_index_a,
         'j': trail_index_b,    # equals 'i' for self-crossings
         'P': (x, y) intersection point,
         'dir_a': unit direction vector at P along one pass,
         'dir_b': unit direction vector at P along the other pass}
    """
    results = []
    n = len(trails)
    lines = [_to_linestring(t.centerline) for t in trails]

    # Inter-trail crossings.
    for i in range(n):
        li = lines[i]
        if li is None:
            continue
        for j in range(i + 1, n):
            lj = lines[j]
            if lj is None:
                continue
            if not li.intersects(lj):
                continue
            for pt in _iter_points(li.intersection(lj)):
                P = (pt.x, pt.y)
                dir_a = _polyline_direction_at(trails[i].centerline, P)
                dir_b = _polyline_direction_at(trails[j].centerline, P)
                if dir_a is None or dir_b is None:
                    continue
                if not _is_real_crossing(dir_a, dir_b):
                    continue
                results.append({'i': i, 'j': j, 'P': P,
                                'dir_a': dir_a, 'dir_b': dir_b})

    # Self-crossings (figure-8 etc.).
    for i in range(n):
        li = lines[i]
        if li is None or li.is_simple:
            continue
        for P in _find_self_intersection_points(li):
            dirs = _two_directions_through(trails[i].centerline, P)
            if len(dirs) < 2:
                continue
            if not _is_real_crossing(dirs[0], dirs[1]):
                continue
            results.append({'i': i, 'j': i, 'P': P,
                            'dir_a': dirs[0], 'dir_b': dirs[1]})

    return results


def _to_linestring(centerline):
    if not centerline or len(centerline) < 2:
        return None
    return LineString(centerline)


def _iter_points(geom):
    """Yield Point objects from any Shapely intersection result.

    LineString / MultiLineString intersections (parallel overlap) are skipped —
    not a realistic case for trail centerlines.
    """
    if geom.is_empty:
        return
    if isinstance(geom, Point):
        yield geom
    elif isinstance(geom, MultiPoint):
        for p in geom.geoms:
            yield p
    elif geom.geom_type == 'GeometryCollection':
        for g in geom.geoms:
            yield from _iter_points(g)


def _polyline_direction_at(centerline, P):
    """Unit tangent vector of the polyline at the point on it nearest to P."""
    px, py = P
    best_d2 = float('inf')
    best_dir = None
    for k in range(len(centerline) - 1):
        ax, ay = centerline[k]
        bx, by = centerline[k + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            continue
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
        qx = ax + t * dx
        qy = ay + t * dy
        d2 = (px - qx) ** 2 + (py - qy) ** 2
        if d2 < best_d2:
            best_d2 = d2
            n = math.hypot(dx, dy)
            best_dir = (dx / n, dy / n) if n > 1e-9 else None
    return best_dir


def _is_real_crossing(dir_a, dir_b):
    """Reject near-parallel pseudo-crossings (trails brushing rather than crossing)."""
    return abs(dir_a[0] * dir_b[1] - dir_a[1] * dir_b[0]) >= 0.05


def _find_self_intersection_points(line):
    """Return (x, y) points where the LineString crosses itself.

    Uses unary_union to split the line at every self-crossing; the resulting
    pieces' endpoints reveal the crossings — a true crossing appears at 4
    piece-endpoints (the line enters and exits twice), whereas the original
    start/end appear at just 1 piece-endpoint each.
    """
    union = unary_union(line)
    if not hasattr(union, 'geoms'):
        return []
    counts = Counter()
    for piece in union.geoms:
        coords = list(piece.coords)
        counts[_quant(coords[0])] += 1
        counts[_quant(coords[-1])] += 1
    line_endpoints = {_quant(line.coords[0]), _quant(line.coords[-1])}
    return [pt for pt, count in counts.items()
            if count >= 4 and pt not in line_endpoints]


def _quant(pt, places=6):
    return (round(pt[0], places), round(pt[1], places))


def _two_directions_through(centerline, P, eps=0.05):
    """Find the two distinct tangent directions of the polyline through P.

    Iterates polyline segments; each segment that contains P (within `eps`)
    contributes its tangent direction.  Adjacent segments give near-parallel
    directions and are deduplicated, so the result has up to 2 entries — the
    two different passes through the self-crossing.
    """
    directions = []
    for k in range(len(centerline) - 1):
        ax, ay = centerline[k]
        bx, by = centerline[k + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            continue
        t = ((P[0] - ax) * dx + (P[1] - ay) * dy) / seg_sq
        if t < 0.0 or t > 1.0:
            continue
        qx = ax + t * dx
        qy = ay + t * dy
        if (P[0] - qx) ** 2 + (P[1] - qy) ** 2 > eps * eps:
            continue
        n = math.hypot(dx, dy)
        if n < 1e-9:
            continue
        d_unit = (dx / n, dy / n)
        # Deduplicate against directions already collected (treat opposites as same).
        is_new = True
        for existing in directions:
            if abs(d_unit[0] * existing[0] + d_unit[1] * existing[1]) > 0.95:
                is_new = False
                break
        if is_new:
            directions.append(d_unit)
        if len(directions) >= 2:
            break
    return directions


def _to_linestring(centerline):
    if not centerline or len(centerline) < 2:
        return None
    return LineString(centerline)


def _iter_points(geom):
    """Yield Point objects from any Shapely intersection result.

    LineString / MultiLineString intersections (parallel overlap) are skipped —
    not a realistic case for trail centerlines.
    """
    if geom.is_empty:
        return
    if isinstance(geom, Point):
        yield geom
    elif isinstance(geom, MultiPoint):
        for p in geom.geoms:
            yield p
    elif geom.geom_type == 'GeometryCollection':
        for g in geom.geoms:
            yield from _iter_points(g)


def _polyline_direction_at(centerline, P):
    """Unit tangent vector of the polyline at the point on it nearest to P."""
    px, py = P
    best_d2 = float('inf')
    best_dir = None
    for k in range(len(centerline) - 1):
        ax, ay = centerline[k]
        bx, by = centerline[k + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            continue
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
        qx = ax + t * dx
        qy = ay + t * dy
        d2 = (px - qx) ** 2 + (py - qy) ** 2
        if d2 < best_d2:
            best_d2 = d2
            n = math.hypot(dx, dy)
            best_dir = (dx / n, dy / n) if n > 1e-9 else None
    return best_dir
