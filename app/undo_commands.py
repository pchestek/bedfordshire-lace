"""Undo/redo command objects for the lace canvas."""
import copy

from PySide6.QtGui import QUndoCommand


def capture_state(item):
    """Return a snapshot of item's state as plain Python types."""
    return item.get_state()


def apply_state(item, state):
    """Restore item from a snapshot and refresh its graphics."""
    item.set_state(state)


def _re_add_to_canvas(canvas, element, item):
    """Add element+item pair back to the canvas element list if not already present."""
    canvas.add_element(element, item)


class AddElementCommand(QUndoCommand):
    """Undo: remove element from scene+canvas. Redo: add it back."""

    def __init__(self, canvas, element, item, description="Add element"):
        super().__init__(description)
        self._canvas = canvas
        self._element = element
        self._item = item

    def redo(self):
        self._canvas.scene().addItem(self._item)
        _re_add_to_canvas(self._canvas, self._element, self._item)

    def undo(self):
        self._canvas.scene().removeItem(self._item)
        self._canvas.remove_element(self._item)


class RemoveElementsCommand(QUndoCommand):
    """Undo: re-add elements to scene+canvas. Redo: remove them."""

    def __init__(self, canvas, pairs, description="Delete"):
        super().__init__(description)
        self._canvas = canvas
        self._pairs = list(pairs)  # [(element, item), ...]

    def redo(self):
        for _, item in self._pairs:
            self._canvas.scene().removeItem(item)
            self._canvas.remove_element(item)

    def undo(self):
        for element, item in self._pairs:
            self._canvas.scene().addItem(item)
            _re_add_to_canvas(self._canvas, element, item)


class EditElementsCommand(QUndoCommand):
    """Undo/redo a set of element data changes.

    changes: list of (item, before_state, after_state)
    """

    def __init__(self, changes, description="Edit"):
        super().__init__(description)
        self._changes = changes

    def redo(self):
        for item, _, after in self._changes:
            apply_state(item, after)

    def undo(self):
        for item, before, _ in self._changes:
            apply_state(item, before)
