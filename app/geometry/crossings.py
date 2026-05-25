"""Trail crossing detection.

Finds points where the centerlines of two trails intersect.  Each intersection
becomes a Crossing element (placed by canvas), with four pinholes in a diamond
around the intersection point: top/bottom apex at the edges of one trail, and
left/right apex at the edges of the other.
"""
import math

from shapely.geometry import LineString, Point, MultiPoint


def find_centerline_intersections(trails):
    """For each pair of trails, return their centerline intersection points.

    trails — list of Trail objects with `.centerline` (list of (x,y)) populated.

    Returns list of dicts:
        {'i': trail_index_a,
         'j': trail_index_b,
         'P': (x, y) intersection point,
         'dir_a': unit direction vector of trail i at P,
         'dir_b': unit direction vector of trail j at P}
    """
    results = []
    n = len(trails)
    lines = [_to_linestring(t.centerline) for t in trails]
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
            inter = li.intersection(lj)
            for pt in _iter_points(inter):
                P = (pt.x, pt.y)
                dir_a = _polyline_direction_at(trails[i].centerline, P)
                dir_b = _polyline_direction_at(trails[j].centerline, P)
                if dir_a is None or dir_b is None:
                    continue
                # Skip near-parallel intersections (trails brushing, not crossing).
                cross = abs(dir_a[0] * dir_b[1] - dir_a[1] * dir_b[0])
                if cross < 0.05:
                    continue
                results.append({'i': i, 'j': j, 'P': P,
                                'dir_a': dir_a, 'dir_b': dir_b})
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
