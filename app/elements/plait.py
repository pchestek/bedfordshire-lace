"""Plait element — data model and Qt graphics item."""
import math

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsItem

from app.elements.base_element import LaceElement, _rot
from app.constants import TRAIL_LINE_WIDTH_MM, PICOT_RADIUS_MM, PIN_SPACING_MM, SELECTION_COLOR


# A plait is 2 pairs; pair_width = PIN_SPACING_MM / 2, so plait half-width = PIN_SPACING_MM / 2
_PLAIT_HALF_WIDTH_MM = PIN_SPACING_MM / 2.0

# Quarter-point positions along the plait where picots may be placed
PICOT_T_VALUES = (0.25, 0.5, 0.75)


class Picot:
    """A single picot on a plait."""

    __slots__ = ('t', 'side')

    def __init__(self, t: float, side: int):
        self.t    = t     # position along plait: one of PICOT_T_VALUES
        self.side = side  # +1 = left side of direction, -1 = right side


class Plait(LaceElement):
    """
    Data model for a plait (straight two-pair braid between two pinholes).

    Attributes
    ----------
    start  : (x, y) mm — first pinhole
    end    : (x, y) mm — second pinhole
    picots : list of Picot
    """

    def __init__(self, start, end):
        super().__init__()
        self.element_type = 'plait'
        self.start  = tuple(start)
        self.end    = tuple(end)
        self.picots = []

    def toggle_picot(self, t: float, side: int):
        """Add a picot at (t, side) if absent; remove it if already present."""
        for i, p in enumerate(self.picots):
            if p.t == t and p.side == side:
                self.picots.pop(i)
                return
        self.picots.append(Picot(t, side))

    def picot_position(self, picot: 'Picot'):
        """Return (x, y) of this picot in scene mm."""
        sx, sy = self.start
        ex, ey = self.end
        px = sx + picot.t * (ex - sx)
        py = sy + picot.t * (ey - sy)
        length = math.hypot(ex - sx, ey - sy)
        if length < 1e-6:
            return (px, py)
        # Unit direction vector
        dx = (ex - sx) / length
        dy = (ey - sy) / length
        # Perpendicular (rotate 90° CCW): (-dy, dx), then scale by side
        nx = -dy * picot.side
        ny =  dx * picot.side
        return (px + nx * _PLAIT_HALF_WIDTH_MM,
                py + ny * _PLAIT_HALF_WIDTH_MM)


class PlaitItem(QGraphicsItem):
    """
    Renders a Plait element on the canvas.
    All coordinates are in mm (scene units).
    """

    def __init__(self, plait: Plait):
        super().__init__()
        self._plait = plait
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def update_data(self, plait: Plait):
        """Replace underlying data and trigger a repaint."""
        self.prepareGeometryChange()
        self._plait = plait
        self.update()

    @property
    def element(self):
        return self._plait

    def get_state(self):
        p = self._plait
        return {
            'type': 'plait',
            'start': p.start,
            'end': p.end,
            'picots': [(pic.t, pic.side) for pic in p.picots],
        }

    def set_state(self, state):
        p = self._plait
        p.start = state['start']
        p.end = state['end']
        p.picots = [Picot(t, s) for t, s in state['picots']]
        self.prepareGeometryChange()
        self.update()

    def pin_positions(self):
        return [self._plait.start, self._plait.end]

    def apply_rotation(self, cx, cy, c, s, orig):
        p = self._plait
        p.start = _rot(cx, cy, c, s, *orig['start'])
        p.end   = _rot(cx, cy, c, s, *orig['end'])
        self.prepareGeometryChange()
        self.update()

    def apply_scale(self, fx, fy, sx, sy, orig):
        p = self._plait
        p.start = (fx + (orig['start'][0] - fx) * sx,
                   fy + (orig['start'][1] - fy) * sy)
        p.end   = (fx + (orig['end'][0] - fx) * sx,
                   fy + (orig['end'][1] - fy) * sy)
        self.prepareGeometryChange()
        self.update()

    def apply_move(self):
        """Sync data model to item pos() after a SelectTool drag."""
        dx = self.pos().x()
        dy = self.pos().y()
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        p = self._plait
        p.start = (p.start[0] + dx, p.start[1] + dy)
        p.end   = (p.end[0]   + dx, p.end[1]   + dy)
        self.prepareGeometryChange()
        self.setPos(0.0, 0.0)
        self.update()

    def boundingRect(self) -> QRectF:
        sx, sy = self._plait.start
        ex, ey = self._plait.end
        margin = _PLAIT_HALF_WIDTH_MM + PICOT_RADIUS_MM + 1.0
        x = min(sx, ex) - margin
        y = min(sy, ey) - margin
        w = max(abs(ex - sx), 0.1) + 2 * margin
        h = max(abs(ey - sy), 0.1) + 2 * margin
        return QRectF(x, y, w, h)

    def paint(self, painter, option, widget=None):
        color = QColor(SELECTION_COLOR) if self.isSelected() else QColor("black")
        pen = QPen(color)
        pen.setWidthF(TRAIL_LINE_WIDTH_MM)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        sx, sy = self._plait.start
        ex, ey = self._plait.end
        painter.drawLine(QPointF(sx, sy), QPointF(ex, ey))

        # Picots — open circles offset perpendicularly from the plait line
        r = PICOT_RADIUS_MM
        for picot in self._plait.picots:
            px, py = self._plait.picot_position(picot)
            painter.drawEllipse(QPointF(px, py), r, r)
