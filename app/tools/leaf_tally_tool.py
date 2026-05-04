"""Leaf tally placement tool — click-drag to define the long axis."""
import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsEllipseItem

from app.tools.base_tool import BaseTool
from app.elements.leaf_tally import LeafTally, LeafTallyItem
from app.constants import SNAP_RADIUS_MM, PINHOLE_RADIUS_MM

_MIN_LENGTH_MM  = 3.0
_SNAP_R         = PINHOLE_RADIUS_MM * 2.5
_START_R        = PINHOLE_RADIUS_MM * 3.0


class LeafTallyTool(BaseTool):
    """
    Click to place pin1 (snaps to nearest pinhole if close), drag toward pin2
    (any angle), release to place (pin2 also snaps to nearest pinhole if close).
    Leaf width = length × ratio, where ratio is set by the options-bar spinner.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._start           = None   # (x, y) of pin1 after press
        self._ratio           = 0.4    # width / length proportion
        self._preview         = None   # LeafTallyItem live preview
        self._snap_indicator  = None   # amber circle — nearest pin on hover
        self._start_indicator = None   # blue circle — confirmed pin1

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        self.cancel()
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def cancel(self):
        self._remove_preview()
        self._remove_item('_snap_indicator')
        self._remove_item('_start_indicator')
        self._start = None

    def set_ratio(self, ratio: float):
        self._ratio = max(0.05, min(1.0, ratio))

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouse_press(self, scene_pos: QPointF, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cx, cy = scene_pos.x(), scene_pos.y()
        nearest = self._nearest_pin(cx, cy)
        self._start = nearest if nearest is not None else (cx, cy)
        self._remove_item('_snap_indicator')
        self._set_start_indicator(*self._start)

    def mouse_move(self, scene_pos: QPointF, event) -> None:
        cx, cy = scene_pos.x(), scene_pos.y()
        nearest = self._nearest_pin(cx, cy)

        if self._start is None:
            # Pre-press: just show hover snap indicator
            if nearest is not None:
                self._set_snap_indicator(*nearest)
            else:
                self._remove_item('_snap_indicator')
            return

        # During drag: snap candidate for pin2
        if nearest is not None:
            self._set_snap_indicator(*nearest)
            tx, ty = nearest
        else:
            self._remove_item('_snap_indicator')
            tx, ty = cx, cy

        sx, sy = self._start
        L = math.hypot(tx - sx, ty - sy)
        if L >= 0.5:
            self._update_preview(sx, sy, tx, ty, L * self._ratio)

    def mouse_release(self, scene_pos: QPointF, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        cx, cy = scene_pos.x(), scene_pos.y()
        nearest = self._nearest_pin(cx, cy)
        ex, ey = nearest if nearest is not None else (cx, cy)

        sx, sy = self._start
        L = math.hypot(ex - sx, ey - sy)
        if L >= _MIN_LENGTH_MM:
            from app.undo_commands import AddElementCommand
            leaf = LeafTally((sx, sy), (ex, ey), L * self._ratio)
            item = LeafTallyItem(leaf)
            self._canvas.undo_stack().push(
                AddElementCommand(self._canvas, leaf, item, "Add leaf tally"))

        self._remove_preview()
        self._remove_item('_start_indicator')
        self._remove_item('_snap_indicator')
        self._start = None

    def mouse_double_click(self, scene_pos: QPointF, event) -> None:
        pass

    # ------------------------------------------------------------------
    # Snap helpers
    # ------------------------------------------------------------------

    def _nearest_pin(self, cx, cy):
        """Return (x, y) of nearest pinhole within SNAP_RADIUS_MM, or None."""
        best_d = SNAP_RADIUS_MM
        best   = None
        for px, py in self._canvas.all_pin_positions():
            d = math.hypot(px - cx, py - cy)
            if d < best_d:
                best_d = d
                best   = (px, py)
        return best

    # ------------------------------------------------------------------
    # Graphics helpers
    # ------------------------------------------------------------------

    def _update_preview(self, x1, y1, x2, y2, width):
        leaf = LeafTally((x1, y1), (x2, y2), width)
        if self._preview is None:
            self._preview = LeafTallyItem(leaf)
            self._preview.setOpacity(0.6)
            self._canvas.scene().addItem(self._preview)
        else:
            self._preview.update_data(leaf)

    def _remove_preview(self):
        if self._preview is not None:
            self._canvas.scene().removeItem(self._preview)
            self._preview = None

    def _set_snap_indicator(self, cx, cy):
        scene = self._canvas.scene()
        r = _SNAP_R
        pen = QPen(QColor("#d07020"))
        pen.setWidthF(0.25)
        if self._snap_indicator is None:
            self._snap_indicator = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r)
            self._snap_indicator.setPen(pen)
            self._snap_indicator.setBrush(Qt.BrushStyle.NoBrush)
            scene.addItem(self._snap_indicator)
        else:
            self._snap_indicator.setPen(pen)
            self._snap_indicator.setRect(cx - r, cy - r, 2*r, 2*r)

    def _set_start_indicator(self, cx, cy):
        scene = self._canvas.scene()
        r = _START_R
        pen = QPen(QColor("#2070d0"))
        pen.setWidthF(0.3)
        if self._start_indicator is None:
            self._start_indicator = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r)
            self._start_indicator.setPen(pen)
            self._start_indicator.setBrush(Qt.BrushStyle.NoBrush)
            scene.addItem(self._start_indicator)
        else:
            self._start_indicator.setPen(pen)
            self._start_indicator.setRect(cx - r, cy - r, 2*r, 2*r)

    def _remove_item(self, attr: str):
        item = getattr(self, attr)
        if item is not None:
            self._canvas.scene().removeItem(item)
            setattr(self, attr, None)
