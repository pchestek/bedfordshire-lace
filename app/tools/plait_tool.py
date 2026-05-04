"""Plait drawing and picot placement tool."""
import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem

from app.tools.base_tool import BaseTool
from app.elements.plait import Plait, PlaitItem, PICOT_T_VALUES, _PLAIT_HALF_WIDTH_MM
from app.constants import SNAP_RADIUS_MM, PINHOLE_RADIUS_MM

# Max perpendicular distance from a plait line to count as a "body click"
_BODY_CLICK_RADIUS_MM = _PLAIT_HALF_WIDTH_MM + 2.0

_SNAP_R     = PINHOLE_RADIUS_MM * 2.5  # visual radius of snap indicator
_START_R    = PINHOLE_RADIUS_MM * 3.0  # visual radius of start-pin indicator


class PlaitTool(BaseTool):
    """
    Click a pinhole → start a plait.
    Click another pinhole → finish the plait.
    Click near the body of an existing plait → add (or remove) a picot at the
      nearest quarter-point (0.25, 0.5, 0.75) on the nearest side.
    Escape → cancel the in-progress plait.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._start_pin       = None  # (x, y) of first clicked pinhole
        self._rubber_item     = None  # dashed rubber-band line
        self._start_indicator = None  # blue circle at start pin
        self._snap_indicator  = None  # amber circle at nearest snap target

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        self._clear_all()
        self._start_pin = None
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def cancel(self):
        self._clear_all()
        self._start_pin = None

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouse_press(self, scene_pos: QPointF, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cx, cy = scene_pos.x(), scene_pos.y()

        # 1. Check for pinhole snap
        nearest = self._nearest_pin(cx, cy)
        if nearest is not None:
            if self._start_pin is None:
                self._start_pin = nearest
                self._set_start_indicator(*nearest)
            else:
                if nearest != self._start_pin:
                    from app.undo_commands import AddElementCommand
                    plait = Plait(self._start_pin, nearest)
                    item  = PlaitItem(plait)
                    self._canvas.undo_stack().push(
                        AddElementCommand(self._canvas, plait, item, "Add plait"))
                self._clear_all()
                self._start_pin = None
            return

        # 2. No pin nearby — check if clicking on a plait body (for picot)
        hit = self._find_plait_body_click(cx, cy)
        if hit is not None:
            from app.undo_commands import capture_state, EditElementsCommand
            plait, item, t, side = hit
            before = capture_state(item)
            plait.toggle_picot(t, side)
            item.update_data(plait)
            after = capture_state(item)
            self._canvas.undo_stack().push(
                EditElementsCommand([(item, before, after)], "Toggle picot"))

    def mouse_move(self, scene_pos: QPointF, event) -> None:
        cx, cy = scene_pos.x(), scene_pos.y()
        nearest = self._nearest_pin(cx, cy)

        if nearest is not None:
            self._set_snap_indicator(*nearest)
            tx, ty = nearest
        else:
            self._remove_item('_snap_indicator')
            tx, ty = cx, cy

        if self._start_pin is not None:
            self._set_rubber_band(*self._start_pin, tx, ty)

    def mouse_release(self, scene_pos: QPointF, event) -> None:
        pass

    def mouse_double_click(self, scene_pos: QPointF, event) -> None:
        pass

    # ------------------------------------------------------------------
    # Snap helpers
    # ------------------------------------------------------------------

    def _nearest_pin(self, cx, cy):
        """Return (x, y) of the nearest pinhole within SNAP_RADIUS_MM, or None."""
        best_d = SNAP_RADIUS_MM
        best   = None
        for px, py in self._canvas.all_pin_positions():
            d = math.hypot(px - cx, py - cy)
            if d < best_d:
                best_d = d
                best   = (px, py)
        return best

    def _find_plait_body_click(self, cx, cy):
        """
        Return (plait, item, t_snapped, side) if (cx, cy) falls within
        _BODY_CLICK_RADIUS_MM of any plait's line segment.
        t is snapped to the nearest quarter-point; side is +1 or -1.
        """
        best_dist = _BODY_CLICK_RADIUS_MM
        best      = None

        for plait, item in self._canvas.plaits():
            sx, sy = plait.start
            ex, ey = plait.end
            length = math.hypot(ex - sx, ey - sy)
            if length < 1e-6:
                continue

            dx = ex - sx
            dy = ey - sy
            # Parameter t of nearest point on the (infinite) line
            t_raw = ((cx - sx) * dx + (cy - sy) * dy) / (length * length)
            t_clamped = max(0.0, min(1.0, t_raw))

            # Closest point on segment
            px = sx + t_clamped * dx
            py = sy + t_clamped * dy
            dist = math.hypot(cx - px, cy - py)

            if dist < best_dist:
                t_snap = min(PICOT_T_VALUES, key=lambda q: abs(q - t_raw))
                # Cross product of (direction) × (point - segment start)
                # positive → click is to the left of the direction vector
                cross = dx * (cy - sy) - dy * (cx - sx)
                side  = +1 if cross > 0 else -1
                best_dist = dist
                best = (plait, item, t_snap, side)

        return best

    # ------------------------------------------------------------------
    # Graphics helpers
    # ------------------------------------------------------------------

    def _set_rubber_band(self, x1, y1, x2, y2):
        scene = self._canvas.scene()
        if self._rubber_item is None:
            pen = QPen(QColor("#4a80c0"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(0.2)
            self._rubber_item = QGraphicsLineItem(x1, y1, x2, y2)
            self._rubber_item.setPen(pen)
            scene.addItem(self._rubber_item)
        else:
            self._rubber_item.setLine(x1, y1, x2, y2)

    def _set_start_indicator(self, cx, cy):
        scene = self._canvas.scene()
        r = _START_R
        pen = QPen(QColor("#2070d0"))
        pen.setWidthF(0.3)
        if self._start_indicator is None:
            self._start_indicator = QGraphicsEllipseItem(
                cx - r, cy - r, 2 * r, 2 * r)
            self._start_indicator.setPen(pen)
            self._start_indicator.setBrush(Qt.BrushStyle.NoBrush)
            scene.addItem(self._start_indicator)
        else:
            self._start_indicator.setPen(pen)
            self._start_indicator.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def _set_snap_indicator(self, cx, cy):
        scene = self._canvas.scene()
        r = _SNAP_R
        pen = QPen(QColor("#d07020"))
        pen.setWidthF(0.25)
        if self._snap_indicator is None:
            self._snap_indicator = QGraphicsEllipseItem(
                cx - r, cy - r, 2 * r, 2 * r)
            self._snap_indicator.setPen(pen)
            self._snap_indicator.setBrush(Qt.BrushStyle.NoBrush)
            scene.addItem(self._snap_indicator)
        else:
            self._snap_indicator.setPen(pen)
            self._snap_indicator.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def _remove_item(self, attr: str):
        item = getattr(self, attr)
        if item is not None:
            self._canvas.scene().removeItem(item)
            setattr(self, attr, None)

    def _clear_all(self):
        for attr in ('_rubber_item', '_start_indicator', '_snap_indicator'):
            self._remove_item(attr)
