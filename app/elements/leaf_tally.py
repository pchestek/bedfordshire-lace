"""Leaf tally element — data model and Qt graphics item."""
import math

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath, QTransform
from PySide6.QtWidgets import QGraphicsItem

from app.elements.base_element import LaceElement, _rot
from app.constants import TRAIL_LINE_WIDTH_MM, PINHOLE_RADIUS_MM, SELECTION_COLOR


def _make_lens_path(pin1, pin2, width):
    """
    Build a QPainterPath for a lens shape (two circular arcs) given the two
    pin endpoints and the perpendicular width at the widest point.
    Returns None if the geometry is degenerate.
    """
    x1, y1 = pin1
    x2, y2 = pin2
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-4 or width < 1e-4:
        return None

    s = min(width / 2, L * 0.49)   # sagitta; clamp so arcs stay valid
    r = (4 * s * s + L * L) / (8 * s)
    offset = r - s                  # distance from chord midpoint to arc center
    alpha = math.degrees(math.atan2(L / 2, offset))

    # ── Canonical path: vertical leaf, pin1 at (0, -L/2), pin2 at (0, +L/2) ──
    path = QPainterPath()
    path.moveTo(0, -L / 2)

    # Left arc: center at (+offset, 0), sweeps from pin1 to pin2 through left bulge
    path.arcTo(QRectF(offset - r, -r, 2 * r, 2 * r),
               180 - alpha, 2 * alpha)

    # Right arc: center at (-offset, 0), sweeps from pin2 to pin1 through right bulge
    path.arcTo(QRectF(-offset - r, -r, 2 * r, 2 * r),
               -alpha, 2 * alpha)

    path.closeSubpath()

    # ── Transform to actual position and angle ─────────────────────────────
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    # Angle of (pin1→pin2) from x-axis; subtract 90° because canonical is vertical
    angle_deg = math.degrees(math.atan2(y2 - y1, x2 - x1)) - 90.0

    t = QTransform()
    t.translate(cx, cy)
    t.rotate(angle_deg)
    return t.map(path)


class LeafTally(LaceElement):
    """
    Data model for a leaf/tally element.

    Attributes
    ----------
    pin1       : (x, y) mm — one end pin
    pin2       : (x, y) mm — other end pin
    leaf_width : float mm — perpendicular width at the widest point
    """

    def __init__(self, pin1, pin2, leaf_width):
        super().__init__()
        self.element_type = 'leaf_tally'
        self.pin1       = tuple(pin1)
        self.pin2       = tuple(pin2)
        self.leaf_width = float(leaf_width)
        # Working order at each endpoint — manual via ▶ marker.
        self.direction_pin1 = 'entry'
        self.direction_pin2 = 'exit'

    def direction_endpoints(self):
        """Yield (x, y, dir_unit_x, dir_unit_y, state, endpoint_id) per end."""
        for ep_id, here, other, state in (
            ('pin1', self.pin1, self.pin2, self.direction_pin1),
            ('pin2', self.pin2, self.pin1, self.direction_pin2),
        ):
            hx, hy = here
            ox, oy = other
            ix, iy = ox - hx, oy - hy
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
        if endpoint_id == 'pin1':
            self.direction_pin1 = 'exit' if self.direction_pin1 == 'entry' else 'entry'
        elif endpoint_id == 'pin2':
            self.direction_pin2 = 'exit' if self.direction_pin2 == 'entry' else 'entry'


class LeafTallyItem(QGraphicsItem):
    """
    Renders a LeafTally as a lens shape with pin dots at the two ends.
    All coordinates are in mm (scene units).
    """

    def __init__(self, leaf: LeafTally):
        super().__init__()
        self._leaf = leaf
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._build()

    def update_data(self, leaf: LeafTally):
        self.prepareGeometryChange()
        self._leaf = leaf
        self._build()
        self.update()

    @property
    def element(self):
        return self._leaf

    def get_state(self):
        lf = self._leaf
        return {
            'type': 'leaf',
            'pin1': lf.pin1,
            'pin2': lf.pin2,
            'leaf_width': lf.leaf_width,
            'direction_pin1': lf.direction_pin1,
            'direction_pin2': lf.direction_pin2,
        }

    def set_state(self, state):
        lf = self._leaf
        lf.pin1 = state['pin1']
        lf.pin2 = state['pin2']
        lf.leaf_width = state['leaf_width']
        lf.direction_pin1 = state.get('direction_pin1', 'entry')
        lf.direction_pin2 = state.get('direction_pin2', 'exit')
        self.prepareGeometryChange()
        self._build()
        self.update()

    def pin_positions(self):
        return [self._leaf.pin1, self._leaf.pin2]

    def apply_rotation(self, cx, cy, c, s, orig):
        lf = self._leaf
        lf.pin1 = _rot(cx, cy, c, s, *orig['pin1'])
        lf.pin2 = _rot(cx, cy, c, s, *orig['pin2'])
        self.prepareGeometryChange()
        self._build()
        self.update()

    def apply_scale(self, fx, fy, sx, sy, orig):
        lf = self._leaf
        lf.pin1 = (fx + (orig['pin1'][0] - fx) * sx,
                   fy + (orig['pin1'][1] - fy) * sy)
        lf.pin2 = (fx + (orig['pin2'][0] - fx) * sx,
                   fy + (orig['pin2'][1] - fy) * sy)
        dx = orig['pin2'][0] - orig['pin1'][0]
        dy = orig['pin2'][1] - orig['pin1'][1]
        L = math.hypot(dx, dy)
        if L > 1e-6:
            perp_scale = math.hypot(-dy / L * sx, dx / L * sy)
            lf.leaf_width = max(0.5, orig['leaf_width'] * perp_scale)
        self.prepareGeometryChange()
        self._build()
        self.update()

    def apply_move(self):
        """Sync data model to item pos() after a SelectTool drag."""
        dx = self.pos().x()
        dy = self.pos().y()
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        lf = self._leaf
        lf.pin1 = (lf.pin1[0] + dx, lf.pin1[1] + dy)
        lf.pin2 = (lf.pin2[0] + dx, lf.pin2[1] + dy)
        self.prepareGeometryChange()
        self._build()
        self.setPos(0.0, 0.0)
        self.update()

    # ------------------------------------------------------------------

    def _build(self):
        self._path = _make_lens_path(
            self._leaf.pin1, self._leaf.pin2, self._leaf.leaf_width)

        # Bounding rect: path bounds + pin radius margin
        # Bounding rect margin includes ~2.5mm for direction-marker triangles.
        if self._path:
            pr = self._path.boundingRect()
            m = PINHOLE_RADIUS_MM + TRAIL_LINE_WIDTH_MM + 2.5
            self._bounding_rect = pr.adjusted(-m, -m, m, m)
        else:
            x1, y1 = self._leaf.pin1
            x2, y2 = self._leaf.pin2
            m = PINHOLE_RADIUS_MM + 2.5
            self._bounding_rect = QRectF(
                min(x1, x2) - m, min(y1, y2) - m,
                abs(x2 - x1) + 2 * m, abs(y2 - y1) + 2 * m)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter, option, widget=None):
        color = QColor(SELECTION_COLOR) if self.isSelected() else QColor("black")
        pen = QPen(color)
        pen.setWidthF(TRAIL_LINE_WIDTH_MM)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._path:
            painter.drawPath(self._path)

        # Pin dots at the two pointed ends
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        r = PINHOLE_RADIUS_MM
        x1, y1 = self._leaf.pin1
        x2, y2 = self._leaf.pin2
        painter.drawEllipse(QPointF(x1, y1), r, r)
        painter.drawEllipse(QPointF(x2, y2), r, r)

        # Direction markers (on-screen only)
        from app import render_state
        if not render_state.output_rendering:
            self._draw_direction_markers(painter)

    def _draw_direction_markers(self, painter):
        APEX = 2.0
        HALF_BASE = 0.8
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#666666")))
        for x, y, dx, dy, _state, _ep in self._leaf.direction_endpoints():
            ax = x + APEX * dx
            ay = y + APEX * dy
            pdx, pdy = -dy, dx
            path = QPainterPath()
            path.moveTo(ax, ay)
            path.lineTo(x + HALF_BASE * pdx, y + HALF_BASE * pdy)
            path.lineTo(x - HALF_BASE * pdx, y - HALF_BASE * pdy)
            path.closeSubpath()
            painter.drawPath(path)
