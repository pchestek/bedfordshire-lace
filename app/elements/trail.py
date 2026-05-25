"""Trail element — data model and Qt graphics item."""
import uuid

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import QGraphicsItem

from app.elements.base_element import LaceElement, _rot
from shapely.geometry import LinearRing as ShapelyLinearRing

from app.geometry.bezier import waypoints_to_bezier, dense_polyline
from app.geometry.offset import offset_polyline
from app.geometry.pinholes import trail_edge_pinholes
from app.constants import PIN_SPACING_MM, PINHOLE_RADIUS_MM, TRAIL_LINE_WIDTH_MM, SELECTION_COLOR

# Fallback pair-width: pair_width = pin_spacing / 2
_PAIR_WIDTH_MM = PIN_SPACING_MM / 2.0

# Minimum path length before geometry is computed (avoids degenerate Shapely calls)
_MIN_PATH_LEN_MM = 2.0


class Trail(LaceElement):
    """
    Data model for a cloth-stitch trail.

    Attributes
    ----------
    waypoints      : list of (x, y) in mm defining the centre path.
    cusps          : list of bool, parallel to waypoints.
                     True = sharp corner (Shift+click) at that point.
    starting_pairs : number of pairs at the beginning of the trail.
    closed         : True if the trail forms a closed loop.
    left_edge      : List[List[(x, y)]] — one or more rendered edge-A polylines.
                     Always a list; non-self-crossing trails have one entry,
                     self-crossing trails (figure-8) have multiple pieces.
    right_edge     : List[List[(x, y)]] — same shape as left_edge.
    pin_positions  : list of pin dicts {'x', 'y', 'side', 'corner'}
    """

    def __init__(self, waypoints, cusps=None, starting_pairs=3, closed=False):
        super().__init__()
        self.element_type   = 'trail'
        self.waypoints      = waypoints
        self.cusps          = cusps if cusps is not None else [False] * len(waypoints)
        self.starting_pairs = starting_pairs
        self.closed         = closed

        self.left_edge     = []
        self.right_edge    = []
        self.centerline    = []  # dense polyline of the centerline (mm); used by crossing detection
        self.half_width    = 0.0
        self.pin_positions = []

    # ------------------------------------------------------------------
    # Geometry computation
    # ------------------------------------------------------------------

    def compute_geometry(self, skip_pinholes=False):
        """(Re)compute edge lines and pinholes from current waypoints."""
        self.left_edge     = []
        self.right_edge    = []
        self.centerline    = []
        self.half_width    = 0.0
        self.pin_positions = []

        if len(self.waypoints) < 2:
            return

        segs = waypoints_to_bezier(self.waypoints, self.cusps, self.closed)
        if not segs:
            return

        # Dense polyline for the Shapely offset
        dense = dense_polyline(segs, step_mm=0.3)
        if len(dense) < 2:
            return

        # Check minimum path length to avoid degenerate Shapely output
        total_len = sum(
            ((dense[i][0] - dense[i-1][0])**2 +
             (dense[i][1] - dense[i-1][1])**2) ** 0.5
            for i in range(1, len(dense))
        )
        if total_len < _MIN_PATH_LEN_MM:
            return

        self.centerline = list(dense)

        trail_width = self.starting_pairs * _PAIR_WIDTH_MM
        half_width  = trail_width / 2.0
        self.half_width = half_width

        if self.closed:
            self._compute_closed_edges(dense, half_width)
        else:
            self.left_edge  = offset_polyline(dense, +half_width)
            self.right_edge = offset_polyline(dense, -half_width)

        # Need at least one non-degenerate piece on each side.
        if not any(len(p) >= 2 for p in self.left_edge) \
                or not any(len(p) >= 2 for p in self.right_edge):
            return

        if not skip_pinholes:
            if len(self.left_edge) == 1 and len(self.right_edge) == 1:
                # Single-piece edges (the common case): use the full
                # centreline-projection algorithm with cusp forcing.
                self.pin_positions = trail_edge_pinholes(
                    self.left_edge[0], self.right_edge[0],
                    PIN_SPACING_MM, segs, half_width,
                    cusps=self.cusps, closed=self.closed)
            else:
                # Multi-piece edges (figure-8 etc.): the centreline-projection
                # approach doesn't generalise across disjoint pieces, so fall
                # back to simple arc-length sampling on each piece.  Loses
                # left/right stagger matching but ensures every edge has pins.
                self.pin_positions = []
                for piece in self.left_edge:
                    self.pin_positions.extend(
                        _arc_length_pinholes(piece, PIN_SPACING_MM, 'a'))
                for piece in self.right_edge:
                    self.pin_positions.extend(
                        _arc_length_pinholes(piece, PIN_SPACING_MM, 'b'))

    def _compute_closed_edges(self, dense, half_width):
        """
        Compute edges for a closed trail using Shapely buffer().

        offset_curve() on a LinearRing produces an open LineString (gap at
        the join point).  buffer() always returns fully-closed rings for both
        the outer and inner edges, which is what we need here.

        For a self-crossing closed trail (figure-8) buffer returns either:
          • One Polygon with the outer outline as exterior and one interior
            ring per lobe (so all interior holes are kept), or
          • A MultiPolygon (one Polygon per lobe — both kept).
        """
        try:
            ring = ShapelyLinearRing(dense[:-1])   # drop repeated closing point
            buffered = ring.buffer(half_width, join_style='mitre', mitre_limit=3.0)
            if buffered.is_empty:
                return
            from shapely.geometry import MultiPolygon
            polys = list(buffered.geoms) if isinstance(buffered, MultiPolygon) \
                                          else [buffered]
            self.left_edge  = [list(p.exterior.coords) for p in polys]
            self.right_edge = [list(interior.coords)
                               for p in polys for interior in p.interiors]
        except Exception:
            pass


# ------------------------------------------------------------------
# Qt graphics item
# ------------------------------------------------------------------

class TrailItem(QGraphicsItem):
    """
    Renders a Trail element on the canvas.
    All coordinates are in mm (scene units).
    """

    def __init__(self, trail: Trail):
        super().__init__()
        self._trail = trail
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._build_paths()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, trail: Trail):
        """Replace the underlying Trail data and trigger a repaint."""
        self.prepareGeometryChange()
        self._trail = trail
        self._build_paths()
        self.update()

    @property
    def element(self):
        return self._trail

    def get_state(self):
        t = self._trail
        return {
            'type': 'trail',
            'waypoints': list(t.waypoints),
            'cusps': list(t.cusps),
            'starting_pairs': t.starting_pairs,
            'closed': t.closed,
        }

    def set_state(self, state):
        t = self._trail
        t.waypoints = list(state['waypoints'])
        t.cusps = list(state['cusps'])
        t.starting_pairs = state['starting_pairs']
        t.closed = state['closed']
        t.compute_geometry()
        self.prepareGeometryChange()
        self._build_paths()
        self.update()

    def pin_positions(self):
        return [(p['x'], p['y']) for p in self._trail.pin_positions
                if not p.get('suppressed')]

    def apply_rotation(self, cx, cy, c, s, orig):
        t = self._trail
        t.waypoints = [_rot(cx, cy, c, s, x, y) for x, y in orig['waypoints']]
        t.compute_geometry()
        self.prepareGeometryChange()
        self._build_paths()
        self.update()

    def apply_scale(self, fx, fy, sx, sy, orig):
        t = self._trail
        t.waypoints = [(fx + (x - fx) * sx, fy + (y - fy) * sy)
                       for x, y in orig['waypoints']]
        t.compute_geometry()
        self.prepareGeometryChange()
        self._build_paths()
        self.update()

    def apply_move(self):
        """
        Called by SelectTool after a drag.  Translates all stored coordinates
        by the item's current pos() offset, then resets pos() to (0, 0).
        """
        dx = self.pos().x()
        dy = self.pos().y()
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        t = self._trail
        t.waypoints    = [(x + dx, y + dy) for x, y in t.waypoints]
        t.left_edge    = [[(x + dx, y + dy) for x, y in piece] for piece in t.left_edge]
        t.right_edge   = [[(x + dx, y + dy) for x, y in piece] for piece in t.right_edge]
        t.centerline   = [(x + dx, y + dy) for x, y in t.centerline]
        t.pin_positions = [
            {**p, 'x': p['x'] + dx, 'y': p['y'] + dy}
            for p in t.pin_positions
        ]
        self.prepareGeometryChange()
        self._build_paths()
        self.setPos(0.0, 0.0)
        self.update()

    # ------------------------------------------------------------------
    # QGraphicsItem interface
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def shape(self):
        """
        Return only the stroked edge lines and pinhole dots as the hit area.
        This makes the interior of a closed trail transparent to mouse clicks,
        so elements inside the trail can be selected independently.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(TRAIL_LINE_WIDTH_MM + 2.0)   # 1 mm click margin each side

        hit = QPainterPath()
        for path in self._left_paths:
            hit.addPath(stroker.createStroke(path))
        for path in self._right_paths:
            hit.addPath(stroker.createStroke(path))

        r = PINHOLE_RADIUS_MM + 0.8
        for pin in self._trail.pin_positions:
            if pin.get('suppressed'):
                continue
            hit.addEllipse(QPointF(pin['x'], pin['y']), r, r)

        return hit

    def paint(self, painter, option, widget=None):
        color = QColor(SELECTION_COLOR) if self.isSelected() else QColor("black")
        pen = QPen(color)
        pen.setWidthF(TRAIL_LINE_WIDTH_MM)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for path in self._left_paths:
            painter.drawPath(path)
        for path in self._right_paths:
            painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        r = PINHOLE_RADIUS_MM
        for pin in self._trail.pin_positions:
            if pin.get('suppressed'):
                continue
            painter.drawEllipse(QPointF(pin['x'], pin['y']), r, r)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_paths(self):
        self._left_paths  = [p for p in (_make_path(piece) for piece in self._trail.left_edge)  if p]
        self._right_paths = [p for p in (_make_path(piece) for piece in self._trail.right_edge) if p]

        all_pts = [pt for piece in self._trail.left_edge  for pt in piece]
        all_pts += [pt for piece in self._trail.right_edge for pt in piece]
        all_pts += [(p['x'], p['y']) for p in self._trail.pin_positions]

        if not all_pts:
            self._bounding_rect = QRectF()
            return

        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        margin = PINHOLE_RADIUS_MM + TRAIL_LINE_WIDTH_MM + 0.5
        self._bounding_rect = QRectF(
            min(xs) - margin,
            min(ys) - margin,
            max(xs) - min(xs) + 2 * margin,
            max(ys) - min(ys) + 2 * margin,
        )


def _make_path(points):
    """Build a QPainterPath polyline from a list of (x, y) tuples."""
    if len(points) < 2:
        return None
    path = QPainterPath()
    path.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        path.lineTo(x, y)
    return path


def _arc_length_pinholes(polyline, spacing_mm, side):
    """Place pinholes along *polyline* at ~spacing arc-length intervals.

    • Detects sharp vertices (angle change > 60°) as cusp corners and forces
      a pin at each one.
    • Places filler pins at exact `spacing` intervals OUTWARD from each
      corner, stopping at the midpoint to the next corner.  Result: each
      corner is flanked by pins exactly `spacing` apart, symmetric on both
      sides.  In the middle of long inter-corner segments the meeting point
      may have a slightly larger or smaller gap — the trade-off for corner
      symmetry.
    • If there are no corners, falls back to uniform sampling.
    • Closed polylines (first ≈ last) don't double up at the wrap-around.

    Used for multi-piece edges (figure-8 etc.) where the centreline-projection
    algorithm doesn't apply.  Returns pin dicts in the same shape as
    `trail_edge_pinholes`.
    """
    import math
    if len(polyline) < 2:
        return []
    arcs = [0.0]
    for i in range(1, len(polyline)):
        dx = polyline[i][0] - polyline[i - 1][0]
        dy = polyline[i][1] - polyline[i - 1][1]
        arcs.append(arcs[-1] + (dx * dx + dy * dy) ** 0.5)
    total = arcs[-1]
    if total < spacing_mm * 0.5:
        return []

    closed = ((polyline[0][0] - polyline[-1][0]) ** 2 +
              (polyline[0][1] - polyline[-1][1]) ** 2) < 1e-6

    corner_arcs = []
    for i in range(1, len(polyline) - 1):
        v1x = polyline[i][0]     - polyline[i - 1][0]
        v1y = polyline[i][1]     - polyline[i - 1][1]
        v2x = polyline[i + 1][0] - polyline[i][0]
        v2y = polyline[i + 1][1] - polyline[i][1]
        n1 = math.hypot(v1x, v1y); n2 = math.hypot(v2x, v2y)
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        if (v1x * v2x + v1y * v2y) / (n1 * n2) < 0.5:
            corner_arcs.append(arcs[i])

    def point_at(d):
        for k in range(len(arcs) - 1):
            if arcs[k] <= d <= arcs[k + 1]:
                seg = arcs[k + 1] - arcs[k]
                t = (d - arcs[k]) / seg if seg > 1e-9 else 0.0
                ax, ay = polyline[k]
                bx, by = polyline[k + 1]
                return (ax + t * (bx - ax), ay + t * (by - ay))
        return polyline[-1]

    def make_pin(arc, is_corner):
        x, y = point_at(arc)
        return {'x': x, 'y': y, 'side': side, 'corner': is_corner}

    # No corners → simple uniform sampling.
    if not corner_arcs:
        sample_max = (total - spacing_mm * 0.5) if closed else total
        d = 0.0
        pins = []
        while d <= sample_max + 1e-9:
            pins.append(make_pin(d, False))
            d += spacing_mm
        return pins

    # Has corners → walk outward from each at exact spacing, stop at midpoint
    # to the neighbour (so each corner gets symmetric pins).
    sorted_corners = sorted(corner_arcs)
    n = len(sorted_corners)
    seen = []  # list of arc positions, used to dedup
    pins = []

    def record(arc, is_corner):
        for s in seen:
            if abs(arc - s) < spacing_mm * 0.3:
                return
        seen.append(arc)
        pins.append(make_pin(arc, is_corner))

    for c in sorted_corners:
        record(c, True)

    for i, c in enumerate(sorted_corners):
        if closed:
            next_c = sorted_corners[(i + 1) % n]
            if next_c <= c:
                next_c += total
            prev_c = sorted_corners[(i - 1) % n]
            if prev_c >= c:
                prev_c -= total
            forward_mid  = (c + next_c) / 2
            backward_mid = (c + prev_c) / 2
        else:
            next_c = sorted_corners[i + 1] if i + 1 < n else total
            prev_c = sorted_corners[i - 1] if i > 0 else 0.0
            forward_mid  = (c + next_c) / 2 if i + 1 < n else total
            backward_mid = (c + prev_c) / 2 if i > 0 else 0.0

        d = c + spacing_mm
        while d < forward_mid - 1e-9:
            arc = d % total if closed else d
            if not closed and arc > total:
                break
            record(arc, False)
            d += spacing_mm

        d = c - spacing_mm
        while d > backward_mid + 1e-9:
            arc = d % total if closed else d
            if not closed and arc < 0.0:
                break
            record(arc, False)
            d -= spacing_mm

    return pins
