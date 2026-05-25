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
    left_edge      : rendered edge-A polyline [(x, y), ...]
    right_edge     : rendered edge-B polyline [(x, y), ...]
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

        if len(self.left_edge) < 2 or len(self.right_edge) < 2:
            return

        if not skip_pinholes:
            self.pin_positions = trail_edge_pinholes(
                self.left_edge, self.right_edge, PIN_SPACING_MM, segs, half_width,
                cusps=self.cusps, closed=self.closed)

    def _compute_closed_edges(self, dense, half_width):
        """
        Compute edges for a closed trail using Shapely buffer().

        offset_curve() on a LinearRing produces an open LineString (gap at
        the join point).  buffer() always returns fully-closed rings for both
        the outer and inner edges, which is what we need here.
        """
        try:
            ring = ShapelyLinearRing(dense[:-1])   # drop repeated closing point
            buffered = ring.buffer(half_width, join_style='mitre', mitre_limit=3.0)
            if buffered.is_empty:
                return
            # Handle MultiPolygon (degenerate case — take largest piece)
            from shapely.geometry import MultiPolygon
            if isinstance(buffered, MultiPolygon):
                buffered = max(buffered.geoms, key=lambda g: g.area)
            self.left_edge  = list(buffered.exterior.coords)
            interiors = list(buffered.interiors)
            self.right_edge = list(interiors[0].coords) if interiors else []
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
        t.left_edge    = [(x + dx, y + dy) for x, y in t.left_edge]
        t.right_edge   = [(x + dx, y + dy) for x, y in t.right_edge]
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
        if self._left_path:
            hit.addPath(stroker.createStroke(self._left_path))
        if self._right_path:
            hit.addPath(stroker.createStroke(self._right_path))

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

        if self._left_path:
            painter.drawPath(self._left_path)
        if self._right_path:
            painter.drawPath(self._right_path)

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
        self._left_path  = _make_path(self._trail.left_edge)
        self._right_path = _make_path(self._trail.right_edge)

        all_pts = list(self._trail.left_edge) + list(self._trail.right_edge)
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
