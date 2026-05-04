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

    Returns list of (x, y) tuples, or [] on failure / degenerate geometry.
    """
    if len(points) < 2:
        return []
    try:
        line = LineString(points)
        result = line.offset_curve(dist_mm, join_style='mitre', mitre_limit=3.0)
        if result is None or result.is_empty:
            return []
        if isinstance(result, MultiLineString):
            result = max(result.geoms, key=lambda g: g.length)
        return list(result.coords)
    except Exception:
        return []
