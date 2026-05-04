"""Node tool — edit trail waypoints after placement."""
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsItem

from app.tools.base_tool import BaseTool
from app.constants import SELECTION_COLOR

_HANDLE_HALF = 1.5   # handle half-size in mm; each handle is 3 mm × 3 mm total


class NodeHandle(QGraphicsItem):
    """Square (smooth) or diamond (cusp) handle for one trail waypoint."""

    def __init__(self, trail, trail_item, wp_idx: int):
        super().__init__()
        self._trail      = trail
        self._trail_item = trail_item
        self._wp_idx     = wp_idx
        self._is_cusp    = trail.cusps[wp_idx]
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(10)
        x, y = trail.waypoints[wp_idx]
        self.setPos(x, y)

    def boundingRect(self) -> QRectF:
        h = _HANDLE_HALF
        return QRectF(-h, -h, 2 * h, 2 * h)

    def shape(self):
        h = _HANDLE_HALF
        path = QPainterPath()
        if self._is_cusp:
            path.moveTo(0, -h)
            path.lineTo(h, 0)
            path.lineTo(0, h)
            path.lineTo(-h, 0)
            path.closeSubpath()
        else:
            path.addRect(-h, -h, 2 * h, 2 * h)
        return path

    def paint(self, painter, option, widget=None):
        h = _HANDLE_HALF
        fill = QColor(SELECTION_COLOR) if self.isSelected() else QColor("white")
        pen = QPen(QColor("#303030"))
        pen.setWidthF(0.25)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        if self._is_cusp:
            path = QPainterPath()
            path.moveTo(0, -h)
            path.lineTo(h, 0)
            path.lineTo(0, h)
            path.lineTo(-h, 0)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawRect(QRectF(-h, -h, 2 * h, 2 * h))

    def sync_cusp(self):
        """Refresh cusp flag and repaint after an external toggle."""
        self._is_cusp = self._trail.cusps[self._wp_idx]
        self.update()


class NodeTool(BaseTool):
    """
    Edit trail waypoints.

    - Drag a handle to reshape the trail live.
    - Shift+click a handle to toggle smooth ↔ cusp.
    - Click on a trail path (not a handle) to insert a new waypoint there.
    - Delete / Backspace removes the selected waypoint (min 2 must remain).
    - Escape cancels any in-progress drag and deselects all handles.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._handles: list = []
        self._drag_handle = None
        self._drag_scene_start: QPointF | None = None
        self._drag_start_wp: tuple | None = None
        self._drag_before_states = None  # captured at drag start

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
        self._canvas.scene().clearSelection()
        self._build_handles()

    def deactivate(self):
        self._end_drag()
        self._remove_handles()

    def cancel(self):
        self._end_drag()
        for h in self._handles:
            h.setSelected(False)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouse_press(self, scene_pos, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        handle = self._handle_at(scene_pos)

        if handle is not None:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Toggle smooth ↔ cusp
                before = self._capture_all_states()
                handle._trail.cusps[handle._wp_idx] = not handle._trail.cusps[handle._wp_idx]
                handle.sync_cusp()
                self._recompute_trail(handle._trail_item)
                self._push_changes_since(before, "Toggle cusp")
            else:
                # Begin drag — snapshot everything before any movement
                self._drag_before_states = self._capture_all_states()
                self._canvas.scene().clearSelection()
                handle.setSelected(True)
                self._drag_handle      = handle
                self._drag_scene_start = QPointF(scene_pos)
                self._drag_start_wp    = handle._trail.waypoints[handle._wp_idx]
            return

        # No handle hit — check for trail body click (insert waypoint)
        trail_item = self._trail_item_at(scene_pos)
        if trail_item is not None:
            before = self._capture_all_states()
            self._insert_waypoint(trail_item, scene_pos.x(), scene_pos.y())
            self._push_changes_since(before, "Insert waypoint")
            return

        # Empty space — clear selection
        self._canvas.scene().clearSelection()

    def mouse_move(self, scene_pos, event):
        if self._drag_handle is None:
            return
        dx = scene_pos.x() - self._drag_scene_start.x()
        dy = scene_pos.y() - self._drag_scene_start.y()
        ox, oy = self._drag_start_wp
        new_x, new_y = ox + dx, oy + dy
        h = self._drag_handle
        h._trail.waypoints[h._wp_idx] = (new_x, new_y)
        self._recompute_trail(h._trail_item)
        h.setPos(new_x, new_y)

    def mouse_release(self, scene_pos, event):
        if self._drag_handle is not None and self._drag_before_states is not None:
            self._push_changes_since(self._drag_before_states, "Move waypoint")
        self._drag_before_states = None
        self._end_drag()

    def mouse_double_click(self, scene_pos, event):
        pass

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def key_press(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            before = self._capture_all_states()
            self._delete_selected()
            self._push_changes_since(before, "Delete waypoint")
            event.accept()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_handles(self):
        for trail, trail_item in self._canvas.trails():
            for i in range(len(trail.waypoints)):
                h = NodeHandle(trail, trail_item, i)
                self._canvas.scene().addItem(h)
                self._handles.append(h)

    def _remove_handles(self):
        for h in self._handles:
            self._canvas.scene().removeItem(h)
        self._handles.clear()

    def _rebuild_handles_for(self, trail_item):
        """Remove and recreate all handles for one trail (after insert/delete)."""
        remaining = []
        for h in self._handles:
            if h._trail_item is trail_item:
                self._canvas.scene().removeItem(h)
            else:
                remaining.append(h)
        self._handles = remaining

        trail = trail_item._trail
        for i in range(len(trail.waypoints)):
            h = NodeHandle(trail, trail_item, i)
            self._canvas.scene().addItem(h)
            self._handles.append(h)

    def _handle_at(self, scene_pos):
        items = self._canvas.scene().items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            self._canvas.transform(),
        )
        for item in items:
            if isinstance(item, NodeHandle):
                return item
        return None

    def _trail_item_at(self, scene_pos):
        from app.elements.trail import TrailItem
        items = self._canvas.scene().items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            self._canvas.transform(),
        )
        for item in items:
            if isinstance(item, TrailItem):
                return item
        return None

    def _recompute_trail(self, trail_item):
        old_pins = [(p['x'], p['y']) for p in trail_item._trail.pin_positions]
        trail_item._trail.compute_geometry()
        trail_item.prepareGeometryChange()
        trail_item._build_paths()
        trail_item.update()
        new_pins = [(p['x'], p['y']) for p in trail_item._trail.pin_positions]
        if old_pins and new_pins:
            self._update_connected_elements(old_pins, new_pins)

    def _update_connected_elements(self, old_pins, new_pins):
        """
        After a trail reshapes, move plait/leaf tally endpoints that were
        snapped to old pin positions to the nearest corresponding new pin.
        """
        from app.elements.plait import PlaitItem
        from app.elements.leaf_tally import LeafTallyItem

        _SNAP = 0.15  # mm — same threshold as select-tool connected-element movement

        def nearest(ox, oy):
            best_d, best = float('inf'), None
            for nx, ny in new_pins:
                d = math.hypot(nx - ox, ny - oy)
                if d < best_d:
                    best_d, best = d, (nx, ny)
            return best

        for item in self._canvas.scene().items():
            if isinstance(item, PlaitItem):
                p = item._plait
                changed = False
                sx, sy = p.start
                for ox, oy in old_pins:
                    if math.hypot(sx - ox, sy - oy) < _SNAP:
                        new = nearest(ox, oy)
                        if new:
                            p.start = new
                            changed = True
                        break
                ex, ey = p.end
                for ox, oy in old_pins:
                    if math.hypot(ex - ox, ey - oy) < _SNAP:
                        new = nearest(ox, oy)
                        if new:
                            p.end = new
                            changed = True
                        break
                if changed:
                    item.prepareGeometryChange()
                    item.update()

            elif isinstance(item, LeafTallyItem):
                lf = item._leaf
                changed = False
                x1, y1 = lf.pin1
                for ox, oy in old_pins:
                    if math.hypot(x1 - ox, y1 - oy) < _SNAP:
                        new = nearest(ox, oy)
                        if new:
                            lf.pin1 = new
                            changed = True
                        break
                x2, y2 = lf.pin2
                for ox, oy in old_pins:
                    if math.hypot(x2 - ox, y2 - oy) < _SNAP:
                        new = nearest(ox, oy)
                        if new:
                            lf.pin2 = new
                            changed = True
                        break
                if changed:
                    item.prepareGeometryChange()
                    item._build()
                    item.update()

    def _insert_waypoint(self, trail_item, cx, cy):
        """Insert a new smooth waypoint at (cx, cy) on the nearest bezier segment."""
        from app.geometry.bezier import waypoints_to_bezier, bezier_point
        trail = trail_item._trail
        segs = waypoints_to_bezier(trail.waypoints, trail.cusps, trail.closed)
        if not segs:
            return

        best_dist = float('inf')
        best_seg = 0
        for seg_idx, seg in enumerate(segs):
            for k in range(21):
                p = bezier_point(seg, k / 20.0)
                d = math.hypot(float(p[0]) - cx, float(p[1]) - cy)
                if d < best_dist:
                    best_dist = d
                    best_seg = seg_idx

        trail.waypoints.insert(best_seg + 1, (cx, cy))
        trail.cusps.insert(best_seg + 1, False)
        self._recompute_trail(trail_item)
        self._rebuild_handles_for(trail_item)

    def _delete_selected(self):
        """Delete selected waypoints; at least 2 must remain per trail."""
        selected = [h for h in self._handles if h.isSelected()]
        if not selected:
            return

        by_trail: dict = {}
        for h in selected:
            by_trail.setdefault(h._trail_item, []).append(h._wp_idx)

        for trail_item, indices in by_trail.items():
            trail = trail_item._trail
            for idx in sorted(indices, reverse=True):
                if len(trail.waypoints) <= 2:
                    break
                trail.waypoints.pop(idx)
                trail.cusps.pop(idx)
            self._recompute_trail(trail_item)
            self._rebuild_handles_for(trail_item)

    def _capture_all_states(self):
        from app.undo_commands import capture_state
        return {i: capture_state(i)
                for i in self._canvas.scene().items()
                if hasattr(i, 'apply_move')}

    def _push_changes_since(self, before, description):
        from app.undo_commands import capture_state, EditElementsCommand
        changes = []
        for item, bstate in before.items():
            astate = capture_state(item)
            if bstate != astate:
                changes.append((item, bstate, astate))
        if changes:
            self._canvas.undo_stack().push(EditElementsCommand(changes, description))

    def _end_drag(self):
        self._drag_handle      = None
        self._drag_scene_start = None
        self._drag_start_wp    = None
