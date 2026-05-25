"""Parallel curve offset using Shapely."""
from shapely.geometry import LineString, MultiLineString


def offset_polyline(points, dist_mm):
    """
    Compute a parallel offset of *points* by *dist_mm*.

    Positive distance → left side of the path (in the direction of travel,
    using standard Shapely / mathematical convention: Y increases upward).
    In the application's screen coordinate system (Y increases downward) this
    maps to the visual right side for a rightward-travelling path — the
    labelling is consistent so long as both edges use opposite signs.

    Always returns List[List[(x, y)]] — a list of offset polylines:
      • [] on failure or degenerate geometry
      • [single_polyline] for a non-self-crossing centerline (the common case)
      • [piece1, piece2, ...] when the centerline self-crosses (figure-8 etc.);
        Shapely returns the offset as a MultiLineString and all pieces are
        preserved so the trail's edges render in full.
    """
    if len(points) < 2:
        return []
    try:
        line = LineString(points)
        result = line.offset_curve(dist_mm, join_style='mitre', mitre_limit=3.0)
        if result is None or result.is_empty:
            return []
        if isinstance(result, MultiLineString):
            return _merge_touching_pieces([list(g.coords) for g in result.geoms])
        return [list(result.coords)]
    except Exception:
        return []


def _merge_touching_pieces(pieces, eps=1e-6):
    """Merge offset pieces whose endpoints coincide.

    Shapely's offset_curve sometimes returns a MultiLineString for non-self-
    crossing input where two adjacent pieces share an endpoint (numerical
    artifact).  These get re-joined into one polyline.  Genuinely disjoint
    pieces (figure-8 lobes etc.) are left separate.
    """
    pieces = [list(p) for p in pieces if len(p) >= 2]
    changed = True
    while changed:
        changed = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                a, b = pieces[i], pieces[j]
                if _close(a[-1], b[0], eps):
                    pieces[i] = a + b[1:]
                elif _close(a[0], b[-1], eps):
                    pieces[i] = b + a[1:]
                elif _close(a[-1], b[-1], eps):
                    pieces[i] = a + list(reversed(b))[1:]
                elif _close(a[0], b[0], eps):
                    pieces[i] = list(reversed(b)) + a[1:]
                else:
                    continue
                pieces.pop(j)
                changed = True
                break
            if changed:
                break
    return pieces


def _close(p, q, eps):
    return abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps
