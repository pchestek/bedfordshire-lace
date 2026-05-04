from PySide6.QtCore import Qt
from app.tools.base_tool import BaseTool


class PanTool(BaseTool):
    """Hand tool — drag to pan the canvas."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._last_pos = None

    def activate(self):
        self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    def deactivate(self):
        self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
        self._last_pos = None

    def mouse_press(self, scene_pos, event):
        self._last_pos = event.position().toPoint()
        self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouse_move(self, scene_pos, event):
        if self._last_pos is not None:
            pos = event.position().toPoint()
            delta = pos - self._last_pos
            self._last_pos = pos
            h = self._canvas.horizontalScrollBar()
            v = self._canvas.verticalScrollBar()
            h.setValue(h.value() - delta.x())
            v.setValue(v.value() - delta.y())

    def mouse_release(self, scene_pos, event):
        self._last_pos = None
        self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)
