import copy
import math
from math import cos, sin, radians

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsView, QGraphicsItem

from app.constants import PIN_SPACING_MM, PIN_SNAP_RADIUS_MM
from app.undo_commands import capture_state, EditElementsCommand, RemoveElementsCommand, AddElementCommand
from app.elements.plait import PlaitItem as _PlaitItem
from app.elements.leaf_tally import LeafTallyItem as _LeafTallyItem

from app.tools.base_tool import BaseTool

# Maximum distance (mm) between two pins for them to be considered connected
_CONNECTED_SNAP_MM = 0.15



class SelectTool(BaseTool):
    """
    Click to select an element; Shift+click to add/remove from selection.
    Drag a selected element to move it; connected elements follow automatically.
    Drag on empty canvas to rubber-band-select multiple elements.
    Click on empty canvas to deselect all.
    Tab / Shift+Tab to cycle through elements in z-order.
    Delete or Backspace to remove selected elements.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self._pre_drag_states = None  # {item: state} captured before each drag
        self._overlay         = None  # SelectionOverlay instance

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
        self._canvas.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        # Use item shape() (not bounding rect) for rubber-band hit testing,
        # so trail interiors don't capture the rubber band unexpectedly.
        self._canvas.setRubberBandSelectionMode(
            Qt.ItemSelectionMode.IntersectsItemShape)
        for item in self._canvas.scene().items():
            if hasattr(item, 'apply_move'):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self._canvas.scene().selectionChanged.connect(self._update_handles)

    def deactivate(self):
        self._sync_moved_items()
        self._remove_handles()
        try:
            self._canvas.scene().selectionChanged.disconnect(self._update_handles)
        except RuntimeError:
            pass
        self._canvas.setDragMode(QGraphicsView.DragMode.NoDrag)
        for item in self._canvas.scene().items():
            if hasattr(item, 'apply_move'):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._canvas.scene().clearSelection()

    def cancel(self):
        pass

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouse_press(self, scene_pos, event):
        from app.tools.transform_handles import SelectionOverlay
        self._sync_moved_items()

        # If the click lands on a transform handle, let it handle everything —
        # no pre-drag snapshot and no shift-click interference.
        topmost = self._canvas.scene().itemAt(scene_pos, self._canvas.transform())
        if isinstance(topmost, SelectionOverlay):
            QGraphicsView.mousePressEvent(self._canvas, event)
            return

        # Snapshot all elements so we can detect what moved after release
        all_items = [i for i in self._canvas.scene().items() if hasattr(i, 'apply_move')]
        self._pre_drag_states = {item: capture_state(item) for item in all_items}

        if (event.button() == Qt.MouseButton.LeftButton and
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            # Shift+click: toggle the topmost lace element at this position
            hit = self._top_lace_item_at(scene_pos)
            if hit is not None:
                hit.setSelected(not hit.isSelected())
                return          # don't let Qt clear the rest of the selection

        QGraphicsView.mousePressEvent(self._canvas, event)

    def mouse_move(self, scene_pos, event):
        QGraphicsView.mouseMoveEvent(self._canvas, event)

    def mouse_release(self, scene_pos, event):
        QGraphicsView.mouseReleaseEvent(self._canvas, event)
        self._snap_to_pinholes()
        self._sync_moved_items()

        if self._pre_drag_states is not None:
            changes = []
            for item, before in self._pre_drag_states.items():
                after = capture_state(item)
                if before != after:
                    changes.append((item, before, after))
            if changes:
                self._canvas.undo_stack().push(EditElementsCommand(changes, "Move"))
            self._pre_drag_states = None

        self._update_handles()

    def mouse_double_click(self, scene_pos, event):
        QGraphicsView.mouseDoubleClickEvent(self._canvas, event)

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def key_press(self, event):
        key = event.key()
        if key == Qt.Key.Key_Tab and not event.isAutoRepeat():
            self._cycle_selection(forward=True)
            event.accept()
        elif key == Qt.Key.Key_Backtab and not event.isAutoRepeat():
            self._cycle_selection(forward=False)
            event.accept()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected()
            event.accept()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                     Qt.Key.Key_Up,   Qt.Key.Key_Down):
            if self._nudge_selected(key, event.modifiers()):
                event.accept()   # consumed — don't scroll canvas
            else:
                event.ignore()   # nothing selected — let canvas scroll
        elif key in (Qt.Key.Key_D,) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._duplicate_selected()
            event.accept()
        elif key in (Qt.Key.Key_BracketLeft,  Qt.Key.Key_BraceLeft,
                     Qt.Key.Key_BracketRight, Qt.Key.Key_BraceRight):
            # BraceLeft/Right are the shifted variants ({ and }) on most keyboards
            step = 45.0 if key in (Qt.Key.Key_BraceLeft, Qt.Key.Key_BraceRight) else 5.0
            if key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BraceLeft):
                step = -step   # CCW on screen
            self._rotate_selected(step)
            event.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _top_lace_item_at(self, scene_pos):
        """Return the topmost lace element under scene_pos, or None."""
        items = self._canvas.scene().items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            self._canvas.transform(),
        )
        for item in items:
            if hasattr(item, 'apply_move'):
                return item
        return None

    def _cycle_selection(self, forward: bool):
        """
        Select the next (or previous) lace element in z-order.
        scene().items() is ordered front-to-back, so Tab drills through
        overlapping elements.
        """
        items = [i for i in self._canvas.scene().items()
                 if hasattr(i, 'apply_move')]
        if not items:
            return
        if not forward:
            items = list(reversed(items))

        selected = [i for i in items if i.isSelected()]
        if not selected:
            items[0].setSelected(True)
            return

        last = selected[-1]
        try:
            idx = items.index(last)
        except ValueError:
            idx = -1
        next_item = items[(idx + 1) % len(items)]
        self._canvas.scene().clearSelection()
        next_item.setSelected(True)

    def _delete_selected(self):
        """Remove all selected lace elements from the canvas."""
        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return
        pairs = [(item.element, item) for item in selected]
        self._canvas.undo_stack().push(RemoveElementsCommand(self._canvas, pairs, "Delete"))

    def _nudge_selected(self, key, modifiers=Qt.KeyboardModifier.NoModifier) -> bool:
        """Move selected elements by one pin-spacing step (or 1/10 with Shift). Returns True if anything moved."""
        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return False
        step = PIN_SPACING_MM / 10 if modifiers & Qt.KeyboardModifier.ShiftModifier else PIN_SPACING_MM
        dx = dy = 0.0
        if key == Qt.Key.Key_Left:  dx = -step
        elif key == Qt.Key.Key_Right: dx =  step
        elif key == Qt.Key.Key_Up:   dy = -step
        elif key == Qt.Key.Key_Down: dy =  step

        all_items = [i for i in self._canvas.scene().items() if hasattr(i, 'apply_move')]
        before_states = {item: capture_state(item) for item in all_items}

        for item in selected:
            item.setPos(item.pos().x() + dx, item.pos().y() + dy)
        self._sync_moved_items()

        changes = [(item, before_states[item], capture_state(item))
                   for item in all_items
                   if capture_state(item) != before_states[item]]
        if changes:
            self._canvas.undo_stack().push(EditElementsCommand(changes, "Nudge"))
        return True

    def _duplicate_selected(self):
        """Duplicate selected elements, offset by one pin-spacing, select the copies."""
        from app.elements.trail import Trail, TrailItem
        from app.elements.plait import Plait, PlaitItem, Picot
        from app.elements.leaf_tally import LeafTally, LeafTallyItem

        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return

        offset = PIN_SPACING_MM
        self._canvas.scene().clearSelection()
        self._canvas.undo_stack().beginMacro("Duplicate")

        for item in selected:
            if isinstance(item, TrailItem):
                t = item._trail
                new_t = Trail(
                    waypoints=[(x + offset, y + offset) for x, y in t.waypoints],
                    cusps=list(t.cusps),
                    starting_pairs=t.starting_pairs,
                    closed=t.closed,
                )
                new_t.compute_geometry()
                new_item = TrailItem(new_t)
                self._canvas.undo_stack().push(
                    AddElementCommand(self._canvas, new_t, new_item, "Add trail"))
                new_item.setSelected(True)

            elif isinstance(item, PlaitItem):
                p = item._plait
                new_p = Plait(
                    start=(p.start[0] + offset, p.start[1] + offset),
                    end=(p.end[0]   + offset, p.end[1]   + offset),
                )
                new_p.picots = [Picot(pic.t, pic.side) for pic in p.picots]
                new_item = PlaitItem(new_p)
                self._canvas.undo_stack().push(
                    AddElementCommand(self._canvas, new_p, new_item, "Add plait"))
                new_item.setSelected(True)

            elif isinstance(item, LeafTallyItem):
                lf = item._leaf
                new_lf = LeafTally(
                    pin1=(lf.pin1[0] + offset, lf.pin1[1] + offset),
                    pin2=(lf.pin2[0] + offset, lf.pin2[1] + offset),
                    leaf_width=lf.leaf_width,
                )
                new_item = LeafTallyItem(new_lf)
                self._canvas.undo_stack().push(
                    AddElementCommand(self._canvas, new_lf, new_item, "Add leaf tally"))
                new_item.setSelected(True)

        self._canvas.undo_stack().endMacro()

        # Make new items movable (select tool is active)
        for item in self._canvas.scene().items():
            if hasattr(item, 'apply_move'):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def _rotate_selected(self, angle_deg: float):
        """
        Rotate selected elements by angle_deg degrees (positive = CW on screen)
        around the centre of their collective bounding box.
        """
        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return

        rects = [item.sceneBoundingRect() for item in selected]
        cx = (min(r.left() for r in rects) + max(r.right()  for r in rects)) / 2
        cy = (min(r.top()  for r in rects) + max(r.bottom() for r in rects)) / 2

        θ = radians(angle_deg)
        c, s = cos(θ), sin(θ)

        before_states = {item: item.get_state() for item in selected}
        for item in selected:
            item.apply_rotation(cx, cy, c, s, before_states[item])

        after_states = {item: item.get_state() for item in selected}
        changes = [(item, before_states[item], after_states[item])
                   for item in selected
                   if after_states[item] != before_states[item]]
        if changes:
            self._canvas.undo_stack().push(EditElementsCommand(changes, "Rotate"))
        self._update_handles()

    def _update_handles(self):
        """Recreate transform handles to match the current selection."""
        from app.tools.transform_handles import SelectionOverlay
        self._remove_handles()

        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return

        self._overlay = SelectionOverlay(
            self._canvas, selected, on_release=self._update_handles)
        self._canvas.scene().addItem(self._overlay)

    def _remove_handles(self):
        if self._overlay is not None:
            self._canvas.scene().removeItem(self._overlay)
            self._overlay = None

    def _snap_to_pinholes(self):
        """
        After a drag, snap each selected element so that its nearest pin
        coincides with the nearest unselected pin within PIN_SNAP_RADIUS_MM.
        Only the best (closest) pair triggers the snap; the whole element moves.
        """
        import math as _math
        selected = [i for i in self._canvas.scene().items()
                    if hasattr(i, 'apply_move') and i.isSelected()]
        if not selected:
            return

        unselected_pins = []
        for item in self._canvas.scene().items():
            if hasattr(item, 'pin_positions') and not item.isSelected():
                unselected_pins.extend(item.pin_positions())

        if not unselected_pins:
            return

        for item in selected:
            # pin_positions() returns stored (pre-drag) coords; add current pos() offset
            # to get actual screen positions of the pins after the drag.
            ox, oy = item.pos().x(), item.pos().y()
            best_d = PIN_SNAP_RADIUS_MM
            best_dx = best_dy = 0.0
            found = False
            for px, py in item.pin_positions():
                ax, ay = px + ox, py + oy   # actual screen position
                for ux, uy in unselected_pins:
                    d = _math.hypot(ax - ux, ay - uy)
                    if d < best_d:
                        best_d = d
                        best_dx = ux - ax
                        best_dy = uy - ay
                        found = True
            if found:
                item.setPos(ox + best_dx, oy + best_dy)

    def _sync_moved_items(self):
        """
        Push Qt item positions back into each element's data model.
        Any element whose pin coincides with a moved pin is translated by the
        same delta so connected elements stay joined after a drag.
        """
        all_items = [i for i in self._canvas.scene().items()
                     if hasattr(i, 'apply_move')]

        # Collect (item, dx, dy, old_pins) for every item that actually moved
        moved = []
        for item in all_items:
            dx = item.pos().x()
            dy = item.pos().y()
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                continue
            moved.append((item, dx, dy, item.pin_positions()))

        # Apply moves to the directly-dragged items
        for item, dx, dy, _ in moved:
            item.apply_move()

        if not moved:
            return

        # Propagate to connected (unmoved) elements.
        # Plaits and leaf tallies: move only the endpoint(s) that touched a moved pin,
        # so the other end stays anchored to whatever it was connected to.
        # Trails: move the whole item if any pin matches (trails are rigid).
        moved_set = {item for item, _, _, _ in moved}
        for item in all_items:
            if item in moved_set:
                continue

            if isinstance(item, _PlaitItem):
                p = item._plait
                changed = False
                for _, dx, dy, old_pins in moved:
                    for ox, oy in old_pins:
                        if math.hypot(p.start[0] - ox, p.start[1] - oy) < _CONNECTED_SNAP_MM:
                            p.start = (p.start[0] + dx, p.start[1] + dy)
                            changed = True
                        if math.hypot(p.end[0] - ox, p.end[1] - oy) < _CONNECTED_SNAP_MM:
                            p.end = (p.end[0] + dx, p.end[1] + dy)
                            changed = True
                if changed:
                    item.prepareGeometryChange()
                    item.update()

            elif isinstance(item, _LeafTallyItem):
                lf = item._leaf
                changed = False
                for _, dx, dy, old_pins in moved:
                    for ox, oy in old_pins:
                        if math.hypot(lf.pin1[0] - ox, lf.pin1[1] - oy) < _CONNECTED_SNAP_MM:
                            lf.pin1 = (lf.pin1[0] + dx, lf.pin1[1] + dy)
                            changed = True
                        if math.hypot(lf.pin2[0] - ox, lf.pin2[1] - oy) < _CONNECTED_SNAP_MM:
                            lf.pin2 = (lf.pin2[0] + dx, lf.pin2[1] + dy)
                            changed = True
                if changed:
                    item.prepareGeometryChange()
                    item._build()
                    item.update()

            else:
                # Trail (or future element types): move whole item if any pin matches
                item_pins = item.pin_positions()
                if not item_pins:
                    continue
                for _, dx, dy, old_pins in moved:
                    if any(
                        math.hypot(ix - ox, iy - oy) < _CONNECTED_SNAP_MM
                        for ox, oy in old_pins
                        for ix, iy in item_pins
                    ):
                        item.setPos(dx, dy)
                        item.apply_move()
                        break
