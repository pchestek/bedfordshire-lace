"""Pinhole placement — centreline-projection approach.

Both edges are sampled by projecting the same set of centreline arc-length
positions onto each edge polyline.  This gives:

  - Proper visual stagger: side 'b' uses centreline positions shifted by half
    a spacing, so every 'b' pin appears halfway between adjacent 'a' pins along
    the trail direction — on straight sections AND curves.
  - Matched counts: both sides derive from the same centreline sample set.
  - Corner pins: an explicit centreline sample is inserted at each cusp waypoint
    so both edges are guaranteed a pin right at every sharp corner.

Deduplication (0.55 × spacing)
--------------------------------
At a tight inner corner several consecutive centreline samples may project to
nearly the same point.  The dedup threshold (1.65 mm at default spacing) is
large enough to collapse them AND to catch the closure near-duplicate on closed
trails, while staying well below the nominal 3 mm pin spacing so legitimate
distinct pins are never merged.

Cusp pin forcing — interior waypoints
--------------------------------------
After the regular projections, each interior cusp is handled explicitly using
the analytical mitre formula to find the exact expected corner position on each
edge, then _nearest_on_polyline to the expected position finds the actual
Shapely-generated edge vertex.

  Inner edge (V-notch): expected tip = analytical mitre intersection on the
      concave side.  _nearest_on_polyline returns the V-notch vertex exactly.
  Outer edge (spike):   expected tip = analytical mitre intersection on the
      convex side.  _nearest_on_polyline finds the spike-tip vertex, NOT a
      point on the side of the spike (which is what projecting the centreline
      waypoint finds — it returns the side of the spike at half_width distance,
      not the tip that extends further).

Cusp pin forcing — endpoint waypoints
--------------------------------------
For open trails with a cusp at the first or last waypoint, the mitre formula
is inapplicable (the direction simply reverses at the cap).  Instead, the
actual edge cap vertices (left_edge[0]/[-1], right_edge[0]/[-1]) are used
directly as the corner pin positions.

Corner redistribution
---------------------
At sharp corners the inner edge arc is much shorter than the outer arc, so
centreline projections produce uneven counts and clustering on each side
(inner pins crowd into the V-notch and dedupe out; outer pins spread along
the spike).  _redistribute_corner_pins solves this per-edge: it clears
existing same-side pins within 2.5 * spacing arc-length of the corner, places
the corner pin, then walks outward at exact spacing intervals up to
2 * spacing in each direction.  Both edges processed this way end up with
matched pin counts and visually even spacing around the corner.
"""
import math

from app.geometry.bezier import sample_uniform


def trail_edge_pinholes(left_edge, right_edge, pin_spacing_mm, segs, half_width,
                        cusps=None, closed=False):
    """
    Place staggered pinholes along the two edge polylines.

    left_edge, right_edge — lists of (x, y) from offset_polyline() or buffer().
    pin_spacing_mm        — centreline spacing between same-side consecutive pins.
    segs                  — Bezier segments from waypoints_to_bezier().
    half_width            — trail half-width in mm.
    cusps                 — optional list of bool parallel to waypoints;
                            True = cusp at that waypoint → force corner pin.

    Returns list of dicts:
        {'x': float, 'y': float, 'side': 'a'|'b', 'corner': bool}
    """
    if not segs or not left_edge or not right_edge:
        return []

    # n_dense=50 is sufficient for typical lace trail arcs (spacing 3 mm,
    # trail length 20–150 mm) and keeps interactive recompute fast.
    cl_a = sample_uniform(segs, pin_spacing_mm, n_dense=50, start_offset=0.0)
    cl_b = sample_uniform(segs, pin_spacing_mm, n_dense=50,
                          start_offset=pin_spacing_mm / 2.0)

    # Pre-compute cusp data: cusp position + normalised in/out directions.
    cusp_data = []  # [(wx, wy, d_in, d_out), ...]
    if cusps:
        for i in range(len(segs) - 1):
            if i + 1 < len(cusps) and cusps[i + 1]:
                pt = segs[i][3]
                # Incoming: seg i start → end
                raw_in_x = float(segs[i][3][0]) - float(segs[i][0][0])
                raw_in_y = float(segs[i][3][1]) - float(segs[i][0][1])
                n = math.hypot(raw_in_x, raw_in_y)
                d_in = (raw_in_x / n, raw_in_y / n) if n > 1e-9 else (1.0, 0.0)
                # Outgoing: seg i+1 start → end
                raw_out_x = float(segs[i + 1][3][0]) - float(segs[i + 1][0][0])
                raw_out_y = float(segs[i + 1][3][1]) - float(segs[i + 1][0][1])
                n = math.hypot(raw_out_x, raw_out_y)
                d_out = (raw_out_x / n, raw_out_y / n) if n > 1e-9 else (1.0, 0.0)
                cusp_data.append((float(pt[0]), float(pt[1]), d_in, d_out))

    pins = []
    _DEDUP_MM = pin_spacing_mm * 0.55

    for pt, _ in cl_a:
        x, y = _nearest_on_polyline(left_edge, (float(pt[0]), float(pt[1])))
        _insert_if_not_covered(pins, x, y, 'a', _DEDUP_MM)

    for pt, _ in cl_b:
        x, y = _nearest_on_polyline(right_edge, (float(pt[0]), float(pt[1])))
        _insert_if_not_covered(pins, x, y, 'b', _DEDUP_MM)

    # Compute arc parameterizations if any cusp exists (interior or endpoint).
    has_any_cusp = bool(cusps and any(cusps))
    left_arcs  = _arc_parameterize(left_edge)  if has_any_cusp else []
    right_arcs = _arc_parameterize(right_edge) if has_any_cusp else []

    for wx, wy, d_in, d_out in cusp_data:
        # Compute expected corner positions analytically for each edge, then
        # snap to the actual nearest edge point (handles mitre-clip gracefully).
        expected_a = _compute_offset_corner(wx, wy, d_in, d_out, half_width,
                                            positive=True)
        expected_b = _compute_offset_corner(wx, wy, d_in, d_out, half_width,
                                            positive=False)

        ex_a, ey_a = _nearest_on_polyline(left_edge,  expected_a)
        ex_b, ey_b = _nearest_on_polyline(right_edge, expected_b)

        _redistribute_corner_pins(pins, left_edge,  left_arcs,  'a',
                                  ex_a, ey_a, pin_spacing_mm)
        _redistribute_corner_pins(pins, right_edge, right_arcs, 'b',
                                  ex_b, ey_b, pin_spacing_mm)

    # Endpoint cusps on open trails.  The mitre formula is degenerate at a
    # trail endpoint (the outgoing direction simply reverses), so use the
    # actual edge cap vertices directly instead.
    if not closed and cusps and left_arcs:
        if cusps[-1]:  # cusp at the last waypoint (trail end)
            ex_a, ey_a = left_edge[-1][0],  left_edge[-1][1]
            ex_b, ey_b = right_edge[-1][0], right_edge[-1][1]
            _redistribute_corner_pins(pins, left_edge,  left_arcs,  'a',
                                      ex_a, ey_a, pin_spacing_mm)
            _redistribute_corner_pins(pins, right_edge, right_arcs, 'b',
                                      ex_b, ey_b, pin_spacing_mm)

        if cusps[0]:  # cusp at the first waypoint (trail start)
            ex_a, ey_a = left_edge[0][0],  left_edge[0][1]
            ex_b, ey_b = right_edge[0][0], right_edge[0][1]
            _redistribute_corner_pins(pins, left_edge,  left_arcs,  'a',
                                      ex_a, ey_a, pin_spacing_mm)
            _redistribute_corner_pins(pins, right_edge, right_arcs, 'b',
                                      ex_b, ey_b, pin_spacing_mm)

    return pins


# ── Helpers ──────────────────────────────────────────────────────────────────

def _compute_offset_corner(wx, wy, d_in, d_out, hw, positive):
    """
    Compute the ideal mitre corner position for an offset line at a cusp.

    For offset distance +hw (positive=True, left_edge / side 'a') the normal
    direction is n = (-dy, dx) — Shapely's mathematical left convention applied
    to screen coordinates where positive offset → visual right for rightward
    travel (Y increases downward).

    For negative offset (positive=False, right_edge / side 'b') the normal is
    n = (+dy, -dx).

    The mitre tip is found by intersecting the two offset lines: one offset from
    the incoming segment, one from the outgoing segment.
    """
    if positive:
        nx_in, ny_in   = -d_in[1],  d_in[0]
        nx_out, ny_out = -d_out[1], d_out[0]
    else:
        nx_in, ny_in   =  d_in[1], -d_in[0]
        nx_out, ny_out =  d_out[1], -d_out[0]

    # Solve: hw*n_in + t*d_in = hw*n_out + s*d_out  (intersect the two lines)
    # det = -cross(d_in, d_out)
    det = -(d_in[0] * d_out[1] - d_in[1] * d_out[0])
    if abs(det) < 1e-9:
        return (wx + hw * nx_out, wy + hw * ny_out)

    bx = hw * (nx_out - nx_in)
    by = hw * (ny_out - ny_in)
    t  = (-bx * d_out[1] + by * d_out[0]) / det

    return (wx + hw * nx_in + t * d_in[0],
            wy + hw * ny_in + t * d_in[1])


def _arc_parameterize(points):
    """Cumulative arc lengths at each vertex of a polyline."""
    arcs = [0.0]
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        arcs.append(arcs[-1] + math.hypot(dx, dy))
    return arcs


def _nearest_arc_on_polyline(points, arcs, target):
    """Arc-length position of the nearest point on the polyline to target."""
    tx, ty = target
    best_d2  = float('inf')
    best_arc = 0.0
    for i in range(len(points) - 1):
        ax, ay = points[i]
        bx, by = points[i + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((tx - ax) * dx + (ty - ay) * dy) / seg_sq))
        px = ax + t * dx
        py = ay + t * dy
        d2 = (tx - px) ** 2 + (ty - py) ** 2
        if d2 < best_d2:
            best_d2  = d2
            best_arc = arcs[i] + t * (arcs[i + 1] - arcs[i])
    return best_arc


def _point_at_arc(points, arcs, d):
    """Point on polyline at arc-length d."""
    if d <= 0.0:
        return points[0]
    if d >= arcs[-1]:
        return points[-1]
    for i in range(len(arcs) - 1):
        if arcs[i] <= d <= arcs[i + 1]:
            seg_len = arcs[i + 1] - arcs[i]
            t = (d - arcs[i]) / seg_len if seg_len > 1e-12 else 0.0
            ax, ay = points[i]
            bx, by = points[i + 1]
            return (ax + t * (bx - ax), ay + t * (by - ay))
    return points[-1]


def _redistribute_corner_pins(pins, edge_points, arcs, side,
                              corner_x, corner_y, spacing):
    """Replace corner-zone pins with evenly-arc-spaced pins along the edge.

    Removes all same-side pins within 2.5 * spacing arc-length of the corner,
    inserts the corner pin at its exact position, then walks outward at exact
    spacing arc-length intervals up to 2 * spacing in each direction.  Both
    edges processed this way end up with matched pin counts and visually even
    spacing around the corner; the 0.5 * spacing buffer between the outermost
    redistributed pin and the first surviving regular pin keeps the boundary
    from clumping.
    """
    if not arcs or arcs[-1] < spacing * 0.5:
        return

    corner_arc = _nearest_arc_on_polyline(edge_points, arcs,
                                          (corner_x, corner_y))
    clear_radius = 2.5 * spacing
    walk_radius  = 2.0 * spacing
    zone_min = max(0.0,       corner_arc - clear_radius)
    zone_max = min(arcs[-1],  corner_arc + clear_radius)

    keep = []
    for p in pins:
        if p['side'] != side:
            keep.append(p)
            continue
        p_arc = _nearest_arc_on_polyline(edge_points, arcs, (p['x'], p['y']))
        if not (zone_min <= p_arc <= zone_max):
            keep.append(p)
    pins[:] = keep

    pins.append({'x': corner_x, 'y': corner_y, 'side': side, 'corner': True})

    d = corner_arc - spacing
    while d >= 0.0 and (corner_arc - d) <= walk_radius + 1e-6:
        px, py = _point_at_arc(edge_points, arcs, d)
        pins.append({'x': px, 'y': py, 'side': side, 'corner': False})
        d -= spacing

    d = corner_arc + spacing
    while d <= arcs[-1] and (d - corner_arc) <= walk_radius + 1e-6:
        px, py = _point_at_arc(edge_points, arcs, d)
        pins.append({'x': px, 'y': py, 'side': side, 'corner': False})
        d += spacing


def _nearest_on_polyline(points, target):
    """Nearest point on a polyline (including segment interiors) to target."""
    if not points:
        return target
    if len(points) == 1:
        return points[0]
    tx, ty = target
    best_d2 = float('inf')
    best = points[0]
    for i in range(len(points) - 1):
        ax, ay = points[i]
        bx, by = points[i + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            px, py = ax, ay
        else:
            t = max(0.0, min(1.0, ((tx - ax) * dx + (ty - ay) * dy) / seg_sq))
            px = ax + t * dx
            py = ay + t * dy
        d2 = (tx - px) ** 2 + (ty - py) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = (px, py)
    return best


def _insert_if_not_covered(pins, x, y, side, min_dist):
    """Add a pin at (x, y) if no same-side pin is already within min_dist."""
    for p in pins:
        if p['side'] == side and math.hypot(p['x'] - x, p['y'] - y) < min_dist:
            return
    pins.append({'x': x, 'y': y, 'side': side, 'corner': False})
