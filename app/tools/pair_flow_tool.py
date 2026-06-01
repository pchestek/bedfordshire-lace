"""Pair-flow tool (Stage 12 / Phase A).

Two interactions on a single tool:

1. **Free add / cut events.**  Click a trail pinhole to focus it (blue ring).
   `+` / `=` adds a pair (or increments); `−` / `_` takes one out; pressing
   the opposite key undoes one step; `0` / Delete clears.  Events render as
   `+N` or `−N` text near the pin and drive variable trail width.

2. **Direction flip.**  Click a ▶ marker at an element endpoint to flip its
   working-order direction (entry ↔ exit).  Markers appear at trail / plait /
   leaf-tally endpoints (small triangles); click-through to the marker has
   priority over pin clicks since markers sit outside the pin dot.

Direction-flip clicks push an `EditElementsCommand` so they're undoable.
"""
import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import QGraphicsEllipseItem

from app.elements.trail import Trail, TrailItem
from app.tools.base_tool import BaseTool
from app.undo_commands import EditElementsCommand, capture_state
from app.constants import PINHOLE_RADIUS_MM, SELECTION_COLOR

_FOCUS_RING_R_MM = PINHOLE_RADIUS_MM + 0.9
_PIN_HIT_RADIUS_MM = PINHOLE_RADIUS_MM + 1.5
# Direction-marker hit radius is roughly the triangle's half-length.
_DIR_MARKER_HIT_RADIUS_MM = 2.5


class PairFlowTool(BaseTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        # (item, x, y) of the currently focused trail pin, or None.
        self._focus = None
        self._ring = None

    # ── Tool lifecycle ────────────────────────────────────────────────────────

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)

    def deactivate(self):
        self._clear_focus()
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def cancel(self):
        self._clear_focus()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mouse_press(self, scene_pos, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = scene_pos.x(), scene_pos.y()
        # Direction markers take precedence — they sit outside the pin dot.
        marker = self._find_direction_marker(x, y)
        if marker is not None:
            item, endpoint_id = marker
            self._flip_direction(item, endpoint_id)
            return
        hit = self._find_trail_pin(x, y)
        if hit is None:
            self._clear_focus()
            return
        self._set_focus(*hit)

    def mouse_move(self, scene_pos, event):
        pass

    def mouse_release(self, scene_pos, event):
        pass

    # ── Keys ──────────────────────────────────────────────────────────────────

    def key_press(self, event):
        key = event.key()
        if self._focus is None:
            return
        item, x, y = self._focus
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._apply_event_change(item, x, y, delta_add=1)
            event.accept()
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._apply_event_change(item, x, y, delta_cut=1)
            event.accept()
        elif key in (Qt.Key.Key_0, Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._apply_event_clear(item, x, y)
            event.accept()
        elif key == Qt.Key.Key_Escape:
            self._clear_focus()
            event.accept()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _find_trail_pin(self, x, y):
        """Find the nearest trail pin within _PIN_HIT_RADIUS_MM.

        Returns (TrailItem, pin_x, pin_y) or None.
        """
        best = None
        best_d2 = _PIN_HIT_RADIUS_MM * _PIN_HIT_RADIUS_MM
        for _, item in self._canvas.trails():
            if not isinstance(item, TrailItem):
                continue
            for pin in item.element.pin_positions:
                if pin.get('suppressed'):
                    continue
                px, py = pin['x'], pin['y']
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 <= best_d2:
                    best_d2 = d2
                    best = (item, px, py)
        return best

    def _set_focus(self, item, x, y):
        self._clear_focus()
        self._focus = (item, x, y)
        self._ring = QGraphicsEllipseItem(
            x - _FOCUS_RING_R_MM, y - _FOCUS_RING_R_MM,
            2 * _FOCUS_RING_R_MM, 2 * _FOCUS_RING_R_MM,
        )
        pen = QPen(QColor(SELECTION_COLOR))
        pen.setCosmetic(True)
        pen.setWidth(2)
        self._ring.setPen(pen)
        self._ring.setBrush(Qt.BrushStyle.NoBrush)
        self._ring.setZValue(50)
        self._canvas.scene().addItem(self._ring)

    def _clear_focus(self):
        if self._ring is not None:
            self._canvas.scene().removeItem(self._ring)
            self._ring = None
        self._focus = None

    def _apply_event_change(self, item, x, y, *, delta_add=0, delta_cut=0):
        before = capture_state(item)
        item.element.adjust_free_event(x, y,
                                       delta_add=delta_add,
                                       delta_cut=delta_cut)
        item.update()
        after = capture_state(item)
        if before != after:
            self._canvas.undo_stack().push(
                EditElementsCommand([(item, before, after)], "Pair flow"))

    def _apply_event_clear(self, item, x, y):
        before = capture_state(item)
        item.element.clear_free_event(x, y)
        item.update()
        after = capture_state(item)
        if before != after:
            self._canvas.undo_stack().push(
                EditElementsCommand([(item, before, after)], "Clear pair flow"))

    # ── Direction markers ────────────────────────────────────────────────────

    def _find_direction_marker(self, x, y):
        """Return (item, endpoint_id) of the closest direction marker within
        _DIR_MARKER_HIT_RADIUS_MM of (x, y), or None.

        The marker hit-point is the *centre of the triangle* — endpoint + half
        the apex offset in the direction the arrow points — so clicks land
        naturally on the triangle rather than on the underlying pin dot.
        """
        APEX = 2.0   # mm; matches the triangle apex offset in the painters
        best = None
        best_d2 = _DIR_MARKER_HIT_RADIUS_MM * _DIR_MARKER_HIT_RADIUS_MM
        for _, item in self._canvas._elements:
            element = getattr(item, 'element', None)
            if element is None:
                continue
            endpoints_fn = getattr(element, 'direction_endpoints', None)
            if endpoints_fn is None:
                continue
            for ex, ey, dx, dy, _state, ep_id in endpoints_fn():
                cx = ex + (APEX * 0.5) * dx
                cy = ey + (APEX * 0.5) * dy
                d2 = (x - cx) ** 2 + (y - cy) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = (item, ep_id)
        return best

    def _flip_direction(self, item, endpoint_id):
        before = capture_state(item)
        item.element.flip_direction(endpoint_id)
        item.update()
        after = capture_state(item)
        if before != after:
            self._canvas.undo_stack().push(
                EditElementsCommand([(item, before, after)], "Flip direction"))
