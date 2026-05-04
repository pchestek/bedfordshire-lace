from PySide6.QtCore import QPointF
from PySide6.QtGui import QKeyEvent


class BaseTool:
    """Base class for all canvas tools."""

    def __init__(self, canvas):
        self._canvas = canvas

    def activate(self):
        """Called when this tool becomes active."""

    def deactivate(self):
        """Called when switching away from this tool."""

    def mouse_press(self, scene_pos: QPointF, event) -> None:
        """Mouse button pressed on the canvas."""

    def mouse_move(self, scene_pos: QPointF, event) -> None:
        """Mouse moved on the canvas."""

    def mouse_release(self, scene_pos: QPointF, event) -> None:
        """Mouse button released."""

    def mouse_double_click(self, scene_pos: QPointF, event) -> None:
        """Mouse double-clicked."""

    def cancel(self) -> None:
        """Cancel any in-progress action without leaving the tool."""

    def key_press(self, event: QKeyEvent) -> None:
        """Key pressed while this tool is active."""
