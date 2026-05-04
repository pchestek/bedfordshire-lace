"""Cubic Bezier curve math used throughout the application."""
import numpy as np


def waypoints_to_bezier(points, cusps=None, closed=False):
    """
    Convert waypoints to cubic Bezier segments using Catmull-Rom
    parameterisation.

    points — list of (x, y) waypoints in mm.
    cusps  — optional list of bools (same length as points).
             True = sharp corner at that waypoint; tangent is NOT smoothed.
    closed — if True, generate a closing segment back to points[0] using
             periodic boundary conditions for tangents.

    Returns list of (p0, cp1, cp2, p3) tuples as np.ndarray(2,).
    """
    pts = [np.array(p[:2], dtype=float) for p in points]
    n = len(pts)
    if n < 2:
        return []

    if cusps is None:
        cusps = [False] * n

    if closed:
        # Phantom neighbours wrap around the ends
        ext_pts   = [pts[-1]]   + pts + [pts[0],         pts[1 % n]]
        ext_cusps = [cusps[-1]] + list(cusps) + [cusps[0], cusps[1 % n]]
        num_segs  = n          # includes closing segment back to pts[0]
    else:
        pre  = 2.0 * pts[0]  - pts[1]
        post = 2.0 * pts[-1] - pts[-2]
        ext_pts   = [pre] + pts + [post]
        ext_cusps = [False] + list(cusps) + [False]
        num_segs  = n - 1

    segs = []
    for i in range(1, num_segs + 1):
        p_prev = ext_pts[i - 1]
        p0     = ext_pts[i]
        p3     = ext_pts[i + 1]
        p_next = ext_pts[i + 2] if i + 2 < len(ext_pts) else pts[1 % n]

        is_cusp_p0 = ext_cusps[i]
        is_cusp_p3 = (ext_cusps[i + 1]
                      if i + 1 < len(ext_cusps) else cusps[0])

        # cp1: handle controlling tangent as it LEAVES p0
        if is_cusp_p0:
            cp1 = p0 + (p3 - p0) / 3.0      # straight towards p3
        else:
            cp1 = p0 + (p3 - p_prev) / 6.0

        # cp2: handle controlling tangent as it ARRIVES at p3
        if is_cusp_p3:
            cp2 = p3 - (p3 - p0) / 3.0      # straight from p0
        else:
            cp2 = p3 - (p_next - p0) / 6.0

        segs.append((p0, cp1, cp2, p3))
    return segs


def bezier_point(seg, t):
    p0, c1, c2, p3 = seg
    u = 1.0 - t
    return u**3 * p0 + 3.0*u**2*t*c1 + 3.0*u*t**2*c2 + t**3*p3


def bezier_tangent(seg, t):
    p0, c1, c2, p3 = seg
    u = 1.0 - t
    return 3.0*(u**2*(c1 - p0) + 2.0*u*t*(c2 - c1) + t**2*(p3 - c2))


def sample_uniform(segs, spacing_mm, n_dense=150):
    """
    Sample a bezier path at uniform arc-length intervals of *spacing_mm*.
    Returns list of (point, unit_tangent) pairs as np.ndarray(2,).
    """
    if not segs:
        return []

    raw_pts  = []
    raw_tans = []
    for seg in segs:
        for t in np.linspace(0.0, 1.0, n_dense, endpoint=False):
            raw_pts.append(bezier_point(seg, t))
            raw_tans.append(bezier_tangent(seg, t))
    raw_pts.append(bezier_point(segs[-1], 1.0))
    raw_tans.append(bezier_tangent(segs[-1], 1.0))

    raw_pts  = np.array(raw_pts)
    raw_tans = np.array(raw_tans)

    diffs = np.diff(raw_pts, axis=0)
    arc   = np.concatenate([[0.0], np.cumsum(np.sqrt((diffs**2).sum(axis=1)))])
    total = arc[-1]
    if total < 1e-6:
        return []

    result = []
    d = 0.0
    while d <= total + 1e-9:
        idx = int(np.searchsorted(arc, d, side='right')) - 1
        idx = max(0, min(idx, len(arc) - 2))
        d0, d1 = arc[idx], arc[idx + 1]
        frac = (d - d0) / (d1 - d0) if d1 > d0 else 0.0
        pt  = raw_pts[idx]  + frac * (raw_pts[idx + 1]  - raw_pts[idx])
        tan = raw_tans[idx] + frac * (raw_tans[idx + 1] - raw_tans[idx])
        n = np.linalg.norm(tan)
        tan = tan / n if n > 1e-9 else np.array([1.0, 0.0])
        result.append((pt.copy(), tan))
        d += spacing_mm

    return result


def dense_polyline(segs, step_mm=0.5):
    """
    Densely-sampled list of (x, y) floats for rendering or Shapely offset.
    For closed paths the final point equals the first (the last segment
    returns to the start).
    """
    if not segs:
        return []
    n = max(8, int(20.0 / step_mm))
    pts = []
    for seg in segs:
        for t in np.linspace(0.0, 1.0, n, endpoint=False):
            p = bezier_point(seg, t)
            pts.append((float(p[0]), float(p[1])))
    p = bezier_point(segs[-1], 1.0)
    pts.append((float(p[0]), float(p[1])))
    return pts
