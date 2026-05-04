"""Horizontal and vertical ruler widgets for the lace canvas."""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PySide6.QtWidgets import QWidget

from app.constants import PX_PER_MM, SELECTION_COLOR

RULER_THICKNESS = 20   # pixels — width of VRuler, height of HRuler

_BG    = QColor("#f0f0f0")
_TICK  = QColor("#909090")
_LABEL = QColor("#404040")
_EDGE  = QColor("#b0b0b0")


def _nice_interval(min_mm: float) -> float:
    """Smallest 'nice' mm interval that is >= min_mm."""
    for step in (1, 2, 5, 10, 20, 50, 100, 200):
        if step >= min_mm:
            return float(step)
    return 200.0


class HRuler(QWidget):
    """Horizontal ruler drawn above the canvas viewport."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._cursor_x = None
        self.setFixedHeight(RULER_THICKNESS)

    def update_cursor(self, x_mm, _y_mm):
        self._cursor_x = x_mm
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)

        px_per_mm = PX_PER_MM * self._canvas._zoom
        vp = self._canvas.viewport().rect()
        left_mm  = self._canvas.mapToScene(vp.topLeft()).x()
        right_mm = self._canvas.mapToScene(vp.topRight()).x()

        tick_mm = _nice_interval(50.0 / px_per_mm)

        font = QFont()
        font.setPixelSize(9)
        painter.setFont(font)

        t = math.floor(left_mm / tick_mm) * tick_mm
        while t <= right_mm + tick_mm:
            x = int(self._canvas.mapFromScene(QPointF(t, 0)).x())
            if 0 <= x <= self.width():
                painter.setPen(QPen(_TICK))
                painter.drawLine(x, RULER_THICKNESS - 5, x, RULER_THICKNESS - 1)
                painter.setPen(QPen(_LABEL))
                painter.drawText(x + 2, RULER_THICKNESS - 6, f"{int(t)}")
            t += tick_mm

        if self._cursor_x is not None:
            x = int(self._canvas.mapFromScene(QPointF(self._cursor_x, 0)).x())
            if 0 <= x <= self.width():
                painter.setPen(QPen(QColor(SELECTION_COLOR)))
                painter.drawLine(x, 0, x, RULER_THICKNESS - 1)

        painter.setPen(QPen(_EDGE))
        painter.drawLine(0, RULER_THICKNESS - 1, self.width(), RULER_THICKNESS - 1)


class VRuler(QWidget):
    """Vertical ruler drawn to the left of the canvas viewport."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._cursor_y = None
        self.setFixedWidth(RULER_THICKNESS)

    def update_cursor(self, _x_mm, y_mm):
        self._cursor_y = y_mm
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)

        px_per_mm = PX_PER_MM * self._canvas._zoom
        vp = self._canvas.viewport().rect()
        top_mm    = self._canvas.mapToScene(vp.topLeft()).y()
        bottom_mm = self._canvas.mapToScene(vp.bottomLeft()).y()

        tick_mm = _nice_interval(50.0 / px_per_mm)

        font = QFont()
        font.setPixelSize(9)
        painter.setFont(font)

        t = math.floor(top_mm / tick_mm) * tick_mm
        while t <= bottom_mm + tick_mm:
            y = int(self._canvas.mapFromScene(QPointF(0, t)).y())
            if 0 <= y <= self.height():
                painter.setPen(QPen(_TICK))
                painter.drawLine(RULER_THICKNESS - 5, y, RULER_THICKNESS - 1, y)
                painter.save()
                painter.setPen(QPen(_LABEL))
                painter.translate(RULER_THICKNESS - 6, y - 2)
                painter.rotate(-90)
                painter.drawText(0, 0, f"{int(t)}")
                painter.restore()
            t += tick_mm

        if self._cursor_y is not None:
            y = int(self._canvas.mapFromScene(QPointF(0, self._cursor_y)).y())
            if 0 <= y <= self.height():
                painter.setPen(QPen(QColor(SELECTION_COLOR)))
                painter.drawLine(0, y, RULER_THICKNESS - 1, y)

        painter.setPen(QPen(_EDGE))
        painter.drawLine(RULER_THICKNESS - 1, 0, RULER_THICKNESS - 1, self.height())
