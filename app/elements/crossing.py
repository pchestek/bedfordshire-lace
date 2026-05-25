"""Crossing element — 4 pins at the inside corners of a trail crossing.

Auto-created by the canvas when two trail centerlines intersect.  Not saved,
not directly editable; lives and dies with the underlying trails.

Geometry: at intersection point P with trail a direction d_a (half-width h_a)
and trail b direction d_b (half-width h_b), the four pins sit at the four
points where trail a's edges intersect trail b's edges.  Each pin is the
solution of

    Q = P + u·d_a + v·d_b
    (Q − P) · n_a = α · h_a   →   v = α · h_a / (d_b · n_a)
    (Q − P) · n_b = β · h_b   →   u = β · h_b / (d_a · n_b)

with α, β ∈ {+1, −1}, giving four corners.  For perpendicular trails the
four corners form a square (rotated 45° from the trail axes); for oblique
trails they form a parallelogram.

The crossing is rendered as 4 pin dots only — no outline.
"""
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsItem

from app.elements.base_element import LaceElement
from app.constants import PINHOLE_RADIUS_MM, SELECTION_COLOR


class Crossing(LaceElement):
    def __init__(self, P, dir_a, dir_b, half_a, half_b):
        super().__init__()
        self.element_type = 'crossing'
        self.P      = tuple(P)
        self.dir_a  = tuple(dir_a)
        self.dir_b  = tuple(dir_b)
        self.half_a = float(half_a)
        self.half_b = float(half_b)
        self._compute_pins()

    def update_from(self, P, dir_a, dir_b, half_a, half_b):
        """Refresh derived geometry in place (after trail change)."""
        self.P      = tuple(P)
        self.dir_a  = tuple(dir_a)
        self.dir_b  = tuple(dir_b)
        self.half_a = float(half_a)
        self.half_b = float(half_b)
        self._compute_pins()

    def _compute_pins(self):
        px, py = self.P
        n_ax, n_ay = -self.dir_a[1], self.dir_a[0]
        n_bx, n_by = -self.dir_b[1], self.dir_b[0]

        d_a_dot_n_b = self.dir_a[0] * n_bx + self.dir_a[1] * n_by
        d_b_dot_n_a = self.dir_b[0] * n_ax + self.dir_b[1] * n_ay

        if abs(d_a_dot_n_b) < 1e-9 or abs(d_b_dot_n_a) < 1e-9:
            # Parallel trails — detection filter should make this unreachable.
            self.A = self.B = self.C = self.D = (px, py)
            return

        def corner(alpha, beta):
            u = beta  * self.half_b / d_a_dot_n_b
            v = alpha * self.half_a / d_b_dot_n_a
            return (px + u * self.dir_a[0] + v * self.dir_b[0],
                    py + u * self.dir_a[1] + v * self.dir_b[1])

        self.A = corner(+1, +1)
        self.B = corner(-1, +1)
        self.D = corner(-1, -1)
        self.C = corner(+1, -1)

    def pins(self):
        return [self.A, self.B, self.D, self.C]

    def polygon(self):
        """Parallelogram (overlap region) vertices in winding order A→B→D→C."""
        return [self.A, self.B, self.D, self.C]


class CrossingItem(QGraphicsItem):
    """Renderer for a Crossing.  Not selectable or movable by the user — the
    select tool's filter uses `hasattr(item, 'apply_move')` to identify lace
    items, and this class deliberately omits that method so crossings are
    invisible to selection/delete/move/duplicate/nudge/rotate paths.
    """

    def __init__(self, crossing: Crossing):
        super().__init__()
        self._crossing = crossing
        # Not selectable / movable — derived from trails, lives and dies with them.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def refresh(self):
        """Call after the underlying Crossing's geometry was updated in place."""
        self.prepareGeometryChange()
        self.update()

    @property
    def element(self):
        return self._crossing

    def pin_positions(self):
        return list(self._crossing.pins())

    def boundingRect(self) -> QRectF:
        pts = self._crossing.polygon()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        margin = PINHOLE_RADIUS_MM + 0.5
        return QRectF(min(xs) - margin, min(ys) - margin,
                      max(xs) - min(xs) + 2 * margin,
                      max(ys) - min(ys) + 2 * margin)

    def shape(self):
        # Hit area = small circles around the 4 pin dots, so clicks elsewhere
        # in the crossing region pass through to underlying lace elements.
        path = QPainterPath()
        r = PINHOLE_RADIUS_MM + 0.8
        for x, y in self._crossing.pins():
            path.addEllipse(QPointF(x, y), r, r)
        return path

    def paint(self, painter, option, widget=None):
        color = QColor(SELECTION_COLOR) if self.isSelected() else QColor("black")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        r = PINHOLE_RADIUS_MM
        for x, y in self._crossing.pins():
            painter.drawEllipse(QPointF(x, y), r, r)
