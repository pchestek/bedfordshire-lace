"""Trail drawing tool."""
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem

from app.tools.base_tool import BaseTool
from app.elements.trail import Trail, TrailItem
from app.constants import SNAP_RADIUS_MM, PINHOLE_RADIUS_MM

# Cursor must be at least this far from the first waypoint before the
# live preview appears (prevents degenerate geometry on first click).
_MIN_PREVIEW_MM = 2.0

# Minimum cursor movement to trigger a preview refresh (performance throttle).
_MIN_MOVE_MM = 0.4


class TrailTool(BaseTool):
    """
    Click to add waypoints; Shift+click for a sharp corner (cusp).
    Double-click to finish an open trail.
    Click within snap distance of the first waypoint to close the trail.

    Snap indicators:
      Blue circle  — close-trail snap (cursor near first waypoint).
      Amber circle — endpoint pinhole snap (cursor near a trail-end pin).
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._waypoints      = []    # list of (x, y)
        self._cusps          = []    # list of bool, parallel to _waypoints
        self._preview_item   = None  # TrailItem for live preview
        self._rubber_item    = None  # dashed line from last pt to cursor
        self._indicator_item = None  # snap indicator circle
        self._starting_pairs = 3
        self._last_cursor    = None  # for throttling

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self):
        self._clear_all()
        self._waypoints  = []
        self._cusps      = []
        self._last_cursor = None
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def cancel(self):
        self._clear_all()
        self._waypoints  = []
        self._cusps      = []
        self._last_cursor = None

    def set_starting_pairs(self, n: int):
        self._starting_pairs = max(3, n)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouse_press(self, scene_pos: QPointF, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cx, cy = scene_pos.x(), scene_pos.y()
        is_cusp = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Close the trail if clicking within snap distance of first waypoint
        if len(self._waypoints) >= 2:
            fx, fy = self._waypoints[0]
            if math.hypot(cx - fx, cy - fy) <= SNAP_RADIUS_MM:
                self._finalize(closed=True)
                return

        self._waypoints.append((cx, cy))
        self._cusps.append(is_cusp)
        self._last_cursor = (cx, cy)
        self._update_preview(cx, cy)

    def mouse_move(self, scene_pos: QPointF, event) -> None:
        if not self._waypoints:
            return
        cx, cy = scene_pos.x(), scene_pos.y()

        # Throttle updates
        if self._last_cursor is not None:
            if math.hypot(cx - self._last_cursor[0],
                          cy - self._last_cursor[1]) < _MIN_MOVE_MM:
                return
        self._last_cursor = (cx, cy)
        self._update_preview(cx, cy)

    def mouse_release(self, scene_pos: QPointF, event) -> None:
        pass

    def mouse_double_click(self, scene_pos: QPointF, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # Qt fires a mousePressEvent immediately before mouseDoubleClickEvent for
        # the same physical click, so mouse_press() already added a waypoint at
        # this position.  Remove it — the double-click means "finish", not "add".
        if self._waypoints:
            self._waypoints.pop()
            self._cusps.pop()
        self._finalize(closed=False)

    # ------------------------------------------------------------------
    # Preview update
    # ------------------------------------------------------------------

    def _update_preview(self, cx: float, cy: float):
        scene = self._canvas.scene()

        # ── Close-trail detection ──────────────────────────────────────
        can_close = False
        if len(self._waypoints) >= 2:
            fx, fy = self._waypoints[0]
            if math.hypot(cx - fx, cy - fy) <= SNAP_RADIUS_MM:
                can_close = True
                cx, cy = fx, fy   # snap cursor to first waypoint

        # ── Suppress preview if cursor too close to the first waypoint ─
        if len(self._waypoints) == 1 and not can_close:
            lx, ly = self._waypoints[0]
            if math.hypot(cx - lx, cy - ly) < _MIN_PREVIEW_MM:
                self._clear_all()
                return

        # ── Build preview trail ────────────────────────────────────────
        pts   = self._waypoints + [(cx, cy)]
        cusps = self._cusps + [False]

        trail = Trail(waypoints=pts, cusps=cusps,
                      starting_pairs=self._starting_pairs,
                      closed=can_close)
        trail.compute_geometry(skip_pinholes=True)

        if self._preview_item is None:
            self._preview_item = TrailItem(trail)
            self._preview_item.setOpacity(0.65)
            scene.addItem(self._preview_item)
        else:
            self._preview_item.update_data(trail)

        # ── Pinhole end-snap (only when not closing) ───────────────────
        snap_x, snap_y = cx, cy
        show_snap      = False
        is_close_snap  = can_close

        if can_close:
            snap_x, snap_y = self._waypoints[0]
            show_snap = True
        else:
            snapped = self._find_end_snap(cx, cy)
            if snapped:
                snap_x, snap_y = snapped
                show_snap = True

        # ── Rubber-band line ───────────────────────────────────────────
        if self._waypoints and not can_close:
            lx, ly = self._waypoints[-1]
            self._set_rubber_band(lx, ly, snap_x, snap_y)
        else:
            self._remove_item('_rubber_item')

        # ── Snap indicator circle ──────────────────────────────────────
        if show_snap:
            self._set_indicator(snap_x, snap_y, is_close_snap)
        else:
            self._remove_item('_indicator_item')

    # ------------------------------------------------------------------
    # Snap helpers
    # ------------------------------------------------------------------

    def _find_end_snap(self, cx, cy):
        """
        Return (x, y) if cursor is within SNAP_RADIUS_MM of the centre-line
        endpoint of any finalized open trail, else None.
        """
        candidates = self._canvas.trail_endpoints()
        if not candidates:
            return None

        best_d = SNAP_RADIUS_MM
        best   = None
        for pt in candidates:
            d = math.hypot(pt[0] - cx, pt[1] - cy)
            if d < best_d:
                best_d = d
                best   = (pt[0], pt[1])
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

    def _set_indicator(self, cx, cy, is_close: bool):
        """Show a circle at the snap target. Blue = close, amber = pinhole."""
        if is_close:
            color = QColor("#2070d0")
            r     = SNAP_RADIUS_MM * 0.75
        else:
            color = QColor("#d07020")
            r     = PINHOLE_RADIUS_MM * 2.5

        scene = self._canvas.scene()
        if self._indicator_item is None:
            pen = QPen(color)
            pen.setWidthF(0.25)
            self._indicator_item = QGraphicsEllipseItem(
                cx - r, cy - r, 2 * r, 2 * r)
            self._indicator_item.setPen(pen)
            self._indicator_item.setBrush(Qt.BrushStyle.NoBrush)
            scene.addItem(self._indicator_item)
        else:
            pen = QPen(color)
            pen.setWidthF(0.25)
            self._indicator_item.setPen(pen)
            self._indicator_item.setRect(cx - r, cy - r, 2 * r, 2 * r)
            self._indicator_item.setVisible(True)

    def _remove_item(self, attr: str):
        item = getattr(self, attr)
        if item is not None:
            self._canvas.scene().removeItem(item)
            setattr(self, attr, None)

    def _clear_all(self):
        for attr in ('_preview_item', '_rubber_item', '_indicator_item'):
            self._remove_item(attr)

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------

    def _finalize(self, closed: bool):
        if len(self._waypoints) >= 2:
            from app.undo_commands import AddElementCommand
            trail = Trail(waypoints=list(self._waypoints),
                          cusps=list(self._cusps),
                          starting_pairs=self._starting_pairs,
                          closed=closed)
            trail.compute_geometry()
            item = TrailItem(trail)
            self._canvas.undo_stack().push(
                AddElementCommand(self._canvas, trail, item, "Add trail"))

        self._clear_all()
        self._waypoints  = []
        self._cusps      = []
        self._last_cursor = None
