"""Trail element — data model and Qt graphics item."""
import uuid

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainterPath, QPainterPathStroker
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
    pin_positions  : list of pin dicts {'x', 'y', 'side', 'corner'}.
    free_events    : list of free pair-flow event dicts (Stage 12):
                       {'x', 'y', 'count': int>0, 'is_cut': bool}.
                     Marks a pin where the lacemaker manually adds (is_cut=False)
                     or cuts (is_cut=True) `count` pairs with no connecting
                     plait/tally/junction.  Stored as scene-mm positions so
                     they survive move/rotate/scale; rendered as a small `+N` /
                     `−N` text near the event position.
    """

    def __init__(self, waypoints, cusps=None, starting_pairs=3, closed=False):
        super().__init__()
        self.element_type   = 'trail'
        self.waypoints      = waypoints
        self.cusps          = cusps if cusps is not None else [False] * len(waypoints)
        self.starting_pairs = starting_pairs
        self.closed         = closed

        # Working order at each endpoint — Phase A Option B: user sets manually
        # via the ▶ marker (PairFlowTool); no auto-inference yet.  Default by
        # position: pairs enter at waypoints[0], exit at waypoints[-1].
        self.direction_start = 'entry'
        self.direction_end   = 'exit'

        self.left_edge     = []
        self.right_edge    = []
        self.centerline    = []  # dense polyline of the centerline (mm); used by crossing detection
        self.half_width    = 0.0
        self.pin_positions = []
        self.free_events   = []  # see class docstring; Stage 12 free adds/cuts

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

        # Visible width is driven by PASSIVES only: 1 worker + (N-1) passives.
        # The worker weaves through the passives without taking width.  See
        # design_decisions.md "Pair-flow architecture / Pair counting convention".
        def passive_half_width(pair_count):
            passive_count = max(1, pair_count - 1)
            return (passive_count * _PAIR_WIDTH_MM) / 2.0

        half_width = passive_half_width(self.starting_pairs)
        self.half_width = half_width

        if self.closed:
            # Variable width inside a closed-loop trail is not handled yet —
            # ignore free events for closed trails for now (Phase A scope).
            self._compute_closed_edges(dense, half_width)
        elif not self.free_events:
            # Open trail with no events — single offset on each side.
            self.left_edge  = offset_polyline(dense, +half_width)
            self.right_edge = offset_polyline(dense, -half_width)
        else:
            # Open trail with free events — split the centreline at each event
            # and offset each segment with its own half-width.  Produces
            # multi-piece edges with a visible step at every event pin.
            self.left_edge, self.right_edge = self._compute_variable_width_edges(
                dense, passive_half_width)

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

    # ------------------------------------------------------------------
    # Free pair-flow events (Stage 12)
    # ------------------------------------------------------------------

    def find_free_event(self, x, y, eps_mm=0.05):
        """Return the index of the free_event nearest (x, y) within eps, else None."""
        best_i = None
        best_d2 = eps_mm * eps_mm
        for i, e in enumerate(self.free_events):
            d2 = (e['x'] - x) ** 2 + (e['y'] - y) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best_i = i
        return best_i

    def adjust_free_event(self, x, y, delta_add=0, delta_cut=0):
        """Apply +delta_add adds (or +delta_cut cuts) to the event at (x, y).

        Either creates the event, modifies the count, flips direction, or
        removes the event when its count drops to 0.  delta_add and delta_cut
        are typically +1 or -1.

        Returns the (updated or new) event dict, or None if the event was
        removed entirely.
        """
        i = self.find_free_event(x, y)
        if i is None:
            count = max(0, delta_add - delta_cut)
            is_cut = (delta_cut > delta_add)
            if count == 0:
                return None
            event = {'x': float(x), 'y': float(y),
                     'count': count, 'is_cut': is_cut}
            self.free_events.append(event)
            return event

        e = self.free_events[i]
        signed = (-e['count'] if e['is_cut'] else e['count']) + delta_add - delta_cut
        if signed == 0:
            self.free_events.pop(i)
            return None
        e['count'] = abs(signed)
        e['is_cut'] = (signed < 0)
        return e

    def clear_free_event(self, x, y):
        """Remove the free_event at (x, y) if present."""
        i = self.find_free_event(x, y)
        if i is not None:
            self.free_events.pop(i)

    # ------------------------------------------------------------------
    # Direction markers (Phase A Option B — manual, no auto-inference)
    # ------------------------------------------------------------------

    def direction_endpoints(self):
        """Yield (x, y, dir_unit_x, dir_unit_y, state, endpoint_id) per endpoint.

        Closed-loop trails have no endpoints (deferred — Phase A step 4),
        so they yield nothing here.

        state ∈ {'entry', 'exit'}; endpoint_id ∈ {'start', 'end'}.
        dir_unit is the direction the marker arrow points: for an 'entry'
        endpoint it points INTO the trail; for an 'exit' endpoint it points
        OUT of the trail.
        """
        import math
        if self.closed or len(self.waypoints) < 2:
            return
        for ep_id, here, neighbour, state in (
            ('start', self.waypoints[0],  self.waypoints[1],  self.direction_start),
            ('end',   self.waypoints[-1], self.waypoints[-2], self.direction_end),
        ):
            hx, hy = here
            nx, ny = neighbour
            # Interior-pointing unit vector (from endpoint toward the next waypoint).
            ix, iy = nx - hx, ny - hy
            n = math.hypot(ix, iy)
            if n < 1e-9:
                continue
            ix, iy = ix / n, iy / n
            if state == 'entry':
                dx, dy = ix, iy
            else:
                dx, dy = -ix, -iy
            yield (hx, hy, dx, dy, state, ep_id)

    def flip_direction(self, endpoint_id):
        """Toggle the working-order direction at the given endpoint."""
        if endpoint_id == 'start':
            self.direction_start = 'exit' if self.direction_start == 'entry' else 'entry'
        elif endpoint_id == 'end':
            self.direction_end = 'exit' if self.direction_end == 'entry' else 'entry'

    # ------------------------------------------------------------------

    def _compute_variable_width_edges(self, dense, half_width_for):
        """Offset the centreline piecewise: each segment between free events
        uses its own half-width derived from the running pair count.

        Returns (left_pieces, right_pieces) as the usual List[List[(x, y)]].
        """
        arcs = _polyline_arcs(dense)
        total = arcs[-1] if arcs else 0.0
        if total <= 0.0:
            return [], []

        # Resolve each event to an arc-length position + signed pair delta.
        events = []
        for e in self.free_events:
            arc = _nearest_arc(dense, arcs, (e['x'], e['y']))
            delta = -e['count'] if e['is_cut'] else e['count']
            events.append((arc, delta))
        events.sort(key=lambda x: x[0])

        # Build segments [(start_arc, end_arc, pair_count_in_segment), ...].
        segments = []
        cur_count = self.starting_pairs
        cur_arc = 0.0
        for arc, delta in events:
            if arc > cur_arc + 1e-9:
                segments.append((cur_arc, arc, cur_count))
            cur_count = max(2, cur_count + delta)  # 1 worker + ≥1 passive
            cur_arc = arc
        if cur_arc < total - 1e-9:
            segments.append((cur_arc, total, cur_count))

        if not segments:
            return [], []

        left_pieces  = []
        right_pieces = []
        for start_arc, end_arc, pc in segments:
            sub = _polyline_sub(dense, arcs, start_arc, end_arc)
            if len(sub) < 2:
                continue
            seg_half = half_width_for(pc)
            left_pieces.extend(offset_polyline(sub,  +seg_half))
            right_pieces.extend(offset_polyline(sub, -seg_half))
        return left_pieces, right_pieces

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
            'free_events': [dict(e) for e in t.free_events],
            'direction_start': t.direction_start,
            'direction_end':   t.direction_end,
        }

    def set_state(self, state):
        t = self._trail
        t.waypoints = list(state['waypoints'])
        t.cusps = list(state['cusps'])
        t.starting_pairs = state['starting_pairs']
        t.closed = state['closed']
        t.free_events = [dict(e) for e in state.get('free_events', [])]
        t.direction_start = state.get('direction_start', 'entry')
        t.direction_end   = state.get('direction_end',   'exit')
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
        t.free_events = [
            {**e, 'x': _rot(cx, cy, c, s, e['x'], e['y'])[0],
                  'y': _rot(cx, cy, c, s, e['x'], e['y'])[1]}
            for e in orig.get('free_events', t.free_events)
        ]
        t.compute_geometry()
        self.prepareGeometryChange()
        self._build_paths()
        self.update()

    def apply_scale(self, fx, fy, sx, sy, orig):
        t = self._trail
        t.waypoints = [(fx + (x - fx) * sx, fy + (y - fy) * sy)
                       for x, y in orig['waypoints']]
        t.free_events = [
            {**e, 'x': fx + (e['x'] - fx) * sx,
                  'y': fy + (e['y'] - fy) * sy}
            for e in orig.get('free_events', t.free_events)
        ]
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
        t.free_events  = [
            {**e, 'x': e['x'] + dx, 'y': e['y'] + dy}
            for e in t.free_events
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

        # Stage 12: free pair-flow event markers (text like "+1", "−2") rendered
        # just up-and-to-the-right of each event's pin position.
        if self._trail.free_events:
            font = QFont()
            font.setPixelSize(2)  # ~2mm tall at scene scale
            painter.setFont(font)
            painter.setPen(QPen(color))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for e in self._trail.free_events:
                glyph = ('−' if e['is_cut'] else '+') + str(e['count'])
                painter.drawText(QPointF(e['x'] + 0.6, e['y'] - 0.4), glyph)

        # Direction markers (▶ triangles at each endpoint).  On-screen only —
        # suppressed during print/export via render_state.output_rendering.
        from app import render_state
        if not render_state.output_rendering:
            self._draw_direction_markers(painter)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _draw_direction_markers(self, painter):
        """Draw a small triangle at each endpoint pointing in working order."""
        APEX = 2.0          # mm — apex distance from endpoint
        HALF_BASE = 0.8     # mm — half-width of triangle base
        marker_color = QColor("#666666")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(marker_color))
        for x, y, dx, dy, _state, _ep_id in self._trail.direction_endpoints():
            ax = x + APEX * dx
            ay = y + APEX * dy
            pdx, pdy = -dy, dx
            b1x = x + HALF_BASE * pdx
            b1y = y + HALF_BASE * pdy
            b2x = x - HALF_BASE * pdx
            b2y = y - HALF_BASE * pdy
            path = QPainterPath()
            path.moveTo(ax, ay)
            path.lineTo(b1x, b1y)
            path.lineTo(b2x, b2y)
            path.closeSubpath()
            painter.drawPath(path)

    def _build_paths(self):
        self._left_paths  = [p for p in (_make_path(piece) for piece in self._trail.left_edge)  if p]
        self._right_paths = [p for p in (_make_path(piece) for piece in self._trail.right_edge) if p]

        all_pts = [pt for piece in self._trail.left_edge  for pt in piece]
        all_pts += [pt for piece in self._trail.right_edge for pt in piece]
        all_pts += [(p['x'], p['y']) for p in self._trail.pin_positions]
        # +1 / −1 markers extend a few mm up-and-right of each event pin
        all_pts += [(e['x'] + 4.0, e['y'] - 2.5) for e in self._trail.free_events]

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


def _polyline_arcs(polyline):
    """Cumulative arc lengths at each vertex of *polyline*."""
    arcs = [0.0]
    for i in range(1, len(polyline)):
        dx = polyline[i][0] - polyline[i - 1][0]
        dy = polyline[i][1] - polyline[i - 1][1]
        arcs.append(arcs[-1] + (dx * dx + dy * dy) ** 0.5)
    return arcs


def _nearest_arc(polyline, arcs, target):
    """Arc-length position on *polyline* closest to *target* (x, y)."""
    if len(polyline) < 2:
        return 0.0
    tx, ty = target
    best_d2 = float('inf')
    best_arc = 0.0
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1e-12:
            continue
        t = max(0.0, min(1.0, ((tx - ax) * dx + (ty - ay) * dy) / seg_sq))
        px = ax + t * dx
        py = ay + t * dy
        d2 = (tx - px) ** 2 + (ty - py) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_arc = arcs[i] + t * (arcs[i + 1] - arcs[i])
    return best_arc


def _polyline_sub(polyline, arcs, start_arc, end_arc):
    """Sub-polyline of *polyline* between *start_arc* and *end_arc*.

    Endpoints are interpolated to land exactly at the arc positions.
    """
    if len(polyline) < 2:
        return []
    total = arcs[-1] if arcs else 0.0
    start_arc = max(0.0, start_arc)
    end_arc = min(total, end_arc)
    if start_arc >= end_arc - 1e-9:
        return []

    def at(d):
        if d <= 0.0:
            return polyline[0]
        if d >= total:
            return polyline[-1]
        for i in range(len(arcs) - 1):
            if arcs[i] <= d <= arcs[i + 1]:
                seg = arcs[i + 1] - arcs[i]
                t = (d - arcs[i]) / seg if seg > 1e-9 else 0.0
                ax, ay = polyline[i]
                bx, by = polyline[i + 1]
                return (ax + t * (bx - ax), ay + t * (by - ay))
        return polyline[-1]

    sub = [at(start_arc)]
    for i, a in enumerate(arcs):
        if start_arc + 1e-9 < a < end_arc - 1e-9:
            sub.append(polyline[i])
    sub.append(at(end_arc))
    return sub


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
