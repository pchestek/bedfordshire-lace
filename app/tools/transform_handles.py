"""
SelectionOverlay — bounding-box transform widget for the select tool.

Shows a dashed selection rectangle with:
  • 8 scale handles at corners (TL/TR/BL/BR) and edge midpoints (T/B/L/R)
  • 1 rotation handle (circle) above the top-centre edge

Drag a scale handle to resize/scale the selected elements.
  Shift + corner handle = proportional (aspect-ratio-locked) scale.
Drag the rotation handle to rotate all selected elements around the bbox centre.
  Shift while rotating = snap to 45° increments.
"""
import math
from math import cos, sin, radians, degrees, atan2, hypot, copysign

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import QApplication, QGraphicsItem


# ── Handle layout ──────────────────────────────────────────────────────────────
#
#   TL ─── T ─── TR
#   │             │
#   L    [ROT]    R      ROT is above T, centred
#   │             │
#   BL ─── B ─── BR


class SelectionOverlay(QGraphicsItem):

    _H       = 1.8   # scale handle half-size (mm)
    _ROT_R   = 2.5   # rotation handle radius (mm)
    _ROT_OFF = 6.0   # mm above the top edge

    _SCALE_KEYS = ('TL', 'T', 'TR', 'R', 'BR', 'B', 'BL', 'L')

    _CURSOR = {
        'TL': Qt.CursorShape.SizeFDiagCursor,
        'BR': Qt.CursorShape.SizeFDiagCursor,
        'TR': Qt.CursorShape.SizeBDiagCursor,
        'BL': Qt.CursorShape.SizeBDiagCursor,
        'T':  Qt.CursorShape.SizeVerCursor,
        'B':  Qt.CursorShape.SizeVerCursor,
        'L':  Qt.CursorShape.SizeHorCursor,
        'R':  Qt.CursorShape.SizeHorCursor,
        'ROT': Qt.CursorShape.PointingHandCursor,
    }

    def __init__(self, canvas, selected, on_release=None):
        super().__init__()
        self._canvas     = canvas
        self._selected   = list(selected)
        self._on_release = on_release
        self._mode       = None   # None | 'rotate' | one of _SCALE_KEYS
        self._orig       = {}     # {item: state}
        self._orig_bbox  = None   # (left, top, right, bottom) at drag start
        self._start_ang  = 0.0

        self.setZValue(20)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,   False)
        self.setAcceptHoverEvents(True)
        self.setPos(0, 0)
        self._recompute()

    # ── Geometry ───────────────────────────────────────────────────────────────

    def _recompute(self):
        rects = [item.sceneBoundingRect() for item in self._selected]
        if not rects:
            self._left = self._right = self._top = self._bottom = 0.0
        else:
            self._left   = min(r.left()   for r in rects)
            self._right  = max(r.right()  for r in rects)
            self._top    = min(r.top()    for r in rects)
            self._bottom = max(r.bottom() for r in rects)
        self._cx = (self._left + self._right)  / 2
        self._cy = (self._top  + self._bottom) / 2

    def _handle_centre(self, key):
        L, R, T, B = self._left, self._right, self._top, self._bottom
        cx, cy = self._cx, self._cy
        H = self._H
        return {
            'TL': (L - H, T - H), 'T': (cx, T), 'TR': (R + H, T - H),
            'R':  (R, cy),
            'BR': (R + H, B + H), 'B': (cx, B), 'BL': (L - H, B + H),
            'L':  (L, cy),
            'ROT': (cx, T - self._ROT_OFF),
        }[key]

    def _handle_rect(self, key):
        hx, hy = self._handle_centre(key)
        h = self._H
        return QRectF(hx - h, hy - h, 2 * h, 2 * h)

    def boundingRect(self):
        _, rot_y = self._handle_centre('ROT')
        m = 2 * self._H + 1.0
        return QRectF(
            self._left  - m,
            rot_y - self._ROT_R - 0.5,
            (self._right - self._left) + 2 * m,
            (self._bottom - rot_y + self._ROT_R) + m + 0.5,
        )

    def shape(self):
        path = QPainterPath()
        for key in self._SCALE_KEYS:
            path.addRect(self._handle_rect(key))
        rx, ry = self._handle_centre('ROT')
        path.addEllipse(QPointF(rx, ry), self._ROT_R, self._ROT_R)
        return path

    # ── Painting ───────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        # Dashed bounding rectangle
        dash_pen = QPen(QColor("#4a80c0"))
        dash_pen.setWidthF(0.28)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([4, 4])
        painter.setPen(dash_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(self._left, self._top,
                                self._right - self._left,
                                self._bottom - self._top))

        # Connecting line to rotation handle
        rx, ry = self._handle_centre('ROT')
        painter.setPen(dash_pen)
        painter.drawLine(QPointF(rx, self._top), QPointF(rx, ry + self._ROT_R))

        # Scale handles
        solid = QPen(QColor("#4a80c0"))
        solid.setWidthF(0.28)
        painter.setPen(solid)
        painter.setBrush(QBrush(QColor("white")))
        for key in self._SCALE_KEYS:
            painter.drawRect(self._handle_rect(key))

        # Rotation handle
        painter.drawEllipse(QPointF(rx, ry), self._ROT_R, self._ROT_R)

    # ── Hover (cursor feedback) ────────────────────────────────────────────────

    def hoverMoveEvent(self, event):
        if self._mode is not None:
            return
        key = self._hit_key(event.scenePos())
        QApplication.restoreOverrideCursor()
        if key is not None:
            QApplication.setOverrideCursor(self._CURSOR[key])

    def hoverLeaveEvent(self, event):
        QApplication.restoreOverrideCursor()

    # ── Mouse events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        key = self._hit_key(event.scenePos())
        if key is None:
            event.ignore()
            return

        from app.undo_commands import capture_state
        self._orig = {i: capture_state(i) for i in self._selected}

        if key == 'ROT':
            self._mode = 'rotate'
            sp = event.scenePos()
            self._start_ang = atan2(sp.y() - self._cy, sp.x() - self._cx)
        else:
            self._mode = key
            self._orig_bbox = (self._left, self._top, self._right, self._bottom)

        QApplication.setOverrideCursor(self._CURSOR[key])
        event.accept()

    def mouseMoveEvent(self, event):
        if self._mode is None:
            return
        sp = event.scenePos()
        if self._mode == 'rotate':
            self._do_rotate(sp, event.modifiers())
        else:
            self._do_scale(sp, event.modifiers())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._mode is None:
            return
        QApplication.restoreOverrideCursor()

        from app.undo_commands import capture_state, EditElementsCommand
        changes = [(item, bst, capture_state(item))
                   for item, bst in self._orig.items()
                   if capture_state(item) != bst]
        if changes:
            desc = "Rotate" if self._mode == 'rotate' else "Scale"
            self._canvas.undo_stack().push(EditElementsCommand(changes, desc))

        self._mode = None
        self._orig = {}
        self._orig_bbox = None
        if self._on_release:
            self._on_release()
        event.accept()

    # ── Hit detection ──────────────────────────────────────────────────────────

    def _hit_key(self, scene_pos):
        x, y = scene_pos.x(), scene_pos.y()
        rx, ry = self._handle_centre('ROT')
        if hypot(x - rx, y - ry) <= self._ROT_R + 0.5:
            return 'ROT'
        tol = 0.5
        for key in self._SCALE_KEYS:
            r = self._handle_rect(key).adjusted(-tol, -tol, tol, tol)
            if r.contains(QPointF(x, y)):
                return key
        return None

    # ── Transform operations ───────────────────────────────────────────────────

    def _do_rotate(self, sp, modifiers):
        cur_ang = atan2(sp.y() - self._cy, sp.x() - self._cx)
        total_deg = degrees(cur_ang - self._start_ang)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            total_deg = round(total_deg / 45.0) * 45.0
        θ = radians(total_deg)
        c, s = cos(θ), sin(θ)
        cx, cy = self._cx, self._cy
        for item, orig in self._orig.items():
            item.apply_rotation(cx, cy, c, s, orig)

    def _do_scale(self, sp, modifiers):
        ol, ot, or_, ob = self._orig_bbox
        cx_orig = (ol + or_) / 2
        cy_orig = (ot + ob) / 2
        key = self._mode
        H = self._H

        # Fixed point: opposite corner/edge stays anchored (bbox edge, not handle centre)
        fx, fy = {
            'TL': (or_, ob), 'T': (cx_orig, ob), 'TR': (ol, ob),
            'R':  (ol, cy_orig),
            'BR': (ol, ot),  'B': (cx_orig, ot), 'BL': (or_, ot),
            'L':  (or_, cy_orig),
        }[key]

        # Where the handle visual centre was at drag start (matches _handle_centre)
        ox, oy = {
            'TL': (ol - H, ot - H), 'T': (cx_orig, ot), 'TR': (or_ + H, ot - H),
            'R':  (or_, cy_orig),
            'BR': (or_ + H, ob + H), 'B': (cx_orig, ob), 'BL': (ol - H, ob + H),
            'L':  (ol, cy_orig),
        }[key]

        denom_x = ox - fx
        denom_y = oy - fy
        sx = (sp.x() - fx) / denom_x if abs(denom_x) > 1e-6 else 1.0
        sy = (sp.y() - fy) / denom_y if abs(denom_y) > 1e-6 else 1.0

        # Edge handles scale one axis only
        if key in ('T', 'B'):
            sx = 1.0
        elif key in ('L', 'R'):
            sy = 1.0

        # Shift on corner = proportional (aspect-ratio-locked)
        if modifiers & Qt.KeyboardModifier.ShiftModifier and key in ('TL', 'TR', 'BL', 'BR'):
            mag = max(abs(sx), abs(sy))
            sx = copysign(mag, sx)
            sy = copysign(mag, sy)

        for item, orig in self._orig.items():
            item.apply_scale(fx, fy, sx, sy, orig)
