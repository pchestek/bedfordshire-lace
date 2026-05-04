import math

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QTransform, QPainter, QPen, QColor, QBrush, QUndoStack
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem

from app.constants import (
    PX_PER_MM, DEFAULT_CANVAS_WIDTH_MM, DEFAULT_CANVAS_HEIGHT_MM,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ARROW_KEY_SCROLL_PX, PIN_SPACING_MM,
)
from app.tools.select_tool import SelectTool
from app.tools.pan_tool import PanTool
from app.tools.trail_tool import TrailTool
from app.tools.plait_tool import PlaitTool
from app.tools.leaf_tally_tool import LeafTallyTool
from app.tools.node_tool import NodeTool


class _GridItem(QGraphicsItem):
    """
    Dot grid drawn as a scene item at z=-50, above the white page (z=-100)
    and below all lace elements (z=0+).  Visibility toggled by the Grid action.
    """

    def __init__(self, canvas):
        super().__init__()
        self._canvas = canvas
        self.setZValue(-50)
        # ItemUsesExtendedStyleOption makes option.exposedRect the actual
        # visible area so paint() skips dots outside the viewport.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0,
                      self._canvas._canvas_w,
                      self._canvas._canvas_h)

    def paint(self, painter, option, widget=None):
        zoom = self._canvas._zoom
        if PIN_SPACING_MM * PX_PER_MM * zoom < 4.0:
            return

        exposed = option.exposedRect
        step = PIN_SPACING_MM
        x0 = max(0.0,                    math.floor(exposed.left()   / step) * step)
        x1 = min(self._canvas._canvas_w, math.ceil( exposed.right()  / step) * step)
        y0 = max(0.0,                    math.floor(exposed.top()    / step) * step)
        y1 = min(self._canvas._canvas_h, math.ceil( exposed.bottom() / step) * step)

        dot_r = max(0.15, 1.0 / (PX_PER_MM * zoom))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#909090")))
        x = x0
        while x <= x1 + 1e-6:
            y = y0
            while y <= y1 + 1e-6:
                painter.drawEllipse(QPointF(x, y), dot_r, dot_r)
                y += step
            x += step


class LaceCanvas(QGraphicsView):
    """
    Main drawing canvas. Scene coordinates are in mm.
    The view transform maps mm → screen pixels at the current zoom level.
    At zoom=1.0, 1mm on screen = 1mm in print (assuming 96 DPI display).
    """

    cursor_moved = Signal(float, float)  # (x_mm, y_mm)
    zoom_changed = Signal(float)         # zoom factor
    tool_changed = Signal(str)           # tool name, emitted on every tool switch

    def __init__(self, parent=None):
        scene = QGraphicsScene()
        super().__init__(scene, parent)

        self._scene = scene
        self._zoom = 1.0
        self._canvas_w = DEFAULT_CANVAS_WIDTH_MM
        self._canvas_h = DEFAULT_CANVAS_HEIGHT_MM

        # Tool instances
        self._select_tool = SelectTool(self)
        self._pan_tool = PanTool(self)
        self._node_tool = NodeTool(self)
        self._trail_tool = TrailTool(self)
        self._plait_tool = PlaitTool(self)
        self._leaf_tally_tool = LeafTallyTool(self)
        self._current_tool = self._select_tool
        self._temp_pan_prev = None  # tool active before H-key pan

        # Document data
        self._elements = []  # list of (element, item) for all lace elements

        self._initial_fit_done = False

        self._undo_stack = QUndoStack(self)
        self._undo_stack.indexChanged.connect(self._on_undo_redo)

        self._configure_view()
        self._draw_page_boundary()
        self._grid_item = _GridItem(self)
        self._grid_item.setVisible(False)
        self._scene.addItem(self._grid_item)
        self._update_transform()
        self._current_tool.activate()

        # Claim keyboard focus so shortcuts work without clicking first
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _configure_view(self):
        # Scene rect: page + 10mm border on each side
        self._scene.setSceneRect(
            -10, -10,
            self._canvas_w + 20,
            self._canvas_h + 20,
        )
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor("#d0d0d0")))
        self.setFrameStyle(0)

    def _draw_page_boundary(self):
        """White rectangle representing the printable page."""
        rect = QGraphicsRectItem(0, 0, self._canvas_w, self._canvas_h)
        rect.setBrush(QBrush(QColor("white")))
        pen = QPen(QColor("#999999"))
        pen.setWidth(0)   # cosmetic — always 1 px on screen
        rect.setPen(pen)
        rect.setZValue(-100)
        self._scene.addItem(rect)

    def _update_transform(self):
        scale = PX_PER_MM * self._zoom
        self.setTransform(QTransform().scale(scale, scale))
        self.zoom_changed.emit(self._zoom)

    # ── Tool management ───────────────────────────────────────────────────────

    def set_tool(self, tool):
        if self._current_tool is tool:
            return
        self._current_tool.deactivate()
        self._current_tool = tool
        self._current_tool.activate()
        self.tool_changed.emit(self.current_tool_name())

    def set_tool_by_name(self, name: str):
        mapping = {
            "select":     self._select_tool,
            "pan":        self._pan_tool,
            "node":       self._node_tool,
            "trail":      self._trail_tool,
            "plait":      self._plait_tool,
            "leaf_tally": self._leaf_tally_tool,
        }
        tool = mapping.get(name)
        if tool:
            self.set_tool(tool)

    def current_tool_name(self) -> str:
        if self._current_tool is self._pan_tool:
            return "pan"
        if self._current_tool is self._node_tool:
            return "node"
        if self._current_tool is self._trail_tool:
            return "trail"
        if self._current_tool is self._plait_tool:
            return "plait"
        if self._current_tool is self._leaf_tally_tool:
            return "leaf_tally"
        return "select"

    def add_element(self, element, item):
        """Register an (element, item) pair in the canvas element list."""
        if not any(i is item for _, i in self._elements):
            self._elements.append((element, item))

    def trails(self):
        """Return (trail, item) pairs for all trail elements."""
        from app.elements.trail import TrailItem
        return [(e, i) for e, i in self._elements if isinstance(i, TrailItem)]

    def plaits(self):
        """Return (plait, item) pairs for all plait elements."""
        from app.elements.plait import PlaitItem
        return [(e, i) for e, i in self._elements if isinstance(i, PlaitItem)]

    def all_pin_positions(self):
        """Return all pinhole positions from all elements as (x, y) tuples."""
        return [pos for _, item in self._elements for pos in item.pin_positions()]

    def trail_endpoints(self):
        """
        Return the start and end centre-line waypoints of every finalized
        open trail.  Closed trails are excluded.
        """
        result = []
        for trail, _ in self.trails():
            if not trail.closed and len(trail.waypoints) >= 2:
                result.append(trail.waypoints[0])
                result.append(trail.waypoints[-1])
        return result

    def remove_element(self, item):
        """Remove a single graphics item from the element list."""
        self._elements = [(e, i) for e, i in self._elements if i is not item]

    def clear(self):
        """Remove all lace elements from the canvas."""
        for _, item in self._elements:
            self._scene.removeItem(item)
        self._elements.clear()
        self._undo_stack.clear()

    def undo_stack(self):
        return self._undo_stack

    # ── Output (print / export) ───────────────────────────────────────────────

    def print_page(self):
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        from PySide6.QtGui import QPainter, QPageLayout, QPageSize
        from PySide6.QtCore import QMarginsF

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setFullPage(True)
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.Letter),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0),
        ))
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        self._render_for_output(painter, printer.resolution() / 25.4)
        painter.end()

    def export_pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QPainter, QPageLayout, QPageSize
        from PySide6.QtCore import QMarginsF

        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "", "PDF files (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setFullPage(True)
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.Letter),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0),
        ))
        painter = QPainter(printer)
        self._render_for_output(painter, printer.resolution() / 25.4)
        painter.end()

    def export_svg(self):
        from PySide6.QtSvg import QSvgGenerator
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QRect, QSize

        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG", "", "SVG files (*.svg)")
        if not path:
            return
        # 96 DPI is the SVG/CSS reference pixel density; at this resolution
        # a correctly-sized SVG will print at 1:1 in any standards-compliant viewer.
        dpm = 96.0 / 25.4
        w_px = round(self._canvas_w * dpm)
        h_px = round(self._canvas_h * dpm)
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(QSize(w_px, h_px))
        gen.setViewBox(QRect(0, 0, w_px, h_px))
        gen.setResolution(96)
        painter = QPainter(gen)
        self._render_for_output(painter, dpm)
        painter.end()

    def _render_for_output(self, painter, dpm):
        """Render the canvas page at dpm dots-per-mm onto painter.

        Hides grid and selection handles; items render in their default
        (non-selected) colour so no blue highlighting appears on output.
        """
        from PySide6.QtCore import QRectF

        grid_visible = self._grid_item.isVisible()
        self._grid_item.setVisible(False)

        # Clear selection: removes SelectionOverlay and restores item colours.
        prev_selected = [i for i in self._scene.items() if i.isSelected()]
        self._scene.clearSelection()

        target = QRectF(0, 0, self._canvas_w * dpm, self._canvas_h * dpm)
        source = QRectF(0, 0, self._canvas_w, self._canvas_h)
        self._scene.render(painter, target, source)

        self._grid_item.setVisible(grid_visible)
        for item in prev_selected:
            item.setSelected(True)

    def node_tool(self):
        return self._node_tool

    def trail_tool(self):
        return self._trail_tool

    def plait_tool(self):
        return self._plait_tool

    def leaf_tally_tool(self):
        return self._leaf_tally_tool

    def _on_undo_redo(self):
        """Rebuild tool handles after any undo/redo so they reflect current state."""
        if self._current_tool is self._node_tool:
            self._node_tool._remove_handles()
            self._node_tool._build_handles()
        elif self._current_tool is self._select_tool:
            self._select_tool._update_handles()

    # ── Grid ──────────────────────────────────────────────────────────────────

    def set_grid_visible(self, visible: bool):
        self._grid_item.setVisible(visible)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def zoom_in(self):
        self._zoom = min(ZOOM_MAX, self._zoom * ZOOM_STEP)
        self._update_transform()

    def zoom_out(self):
        self._zoom = max(ZOOM_MIN, self._zoom / ZOOM_STEP)
        self._update_transform()

    def fit_page(self):
        """Zoom so the full page is visible with a small margin."""
        viewport = self.viewport().rect()
        margin_px = 40
        zoom_x = (viewport.width() - margin_px * 2) / (self._canvas_w * PX_PER_MM)
        zoom_y = (viewport.height() - margin_px * 2) / (self._canvas_h * PX_PER_MM)
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, min(zoom_x, zoom_y)))
        self._update_transform()
        self.centerOn(self._canvas_w / 2, self._canvas_h / 2)

    # ── Events ────────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self._current_tool.mouse_press(scene_pos, event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self._current_tool.mouse_move(scene_pos, event)
        self.cursor_moved.emit(scene_pos.x(), scene_pos.y())

    def mouseReleaseEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self._current_tool.mouse_release(scene_pos, event)

    def mouseDoubleClickEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self._current_tool.mouse_double_click(scene_pos, event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_T and not event.isAutoRepeat():
            self.set_tool_by_name("trail")
        elif key == Qt.Key.Key_P and not event.isAutoRepeat():
            self.set_tool_by_name("plait")
        elif key == Qt.Key.Key_L and not event.isAutoRepeat():
            self.set_tool_by_name("leaf_tally")
        elif key == Qt.Key.Key_S and not event.isAutoRepeat():
            self.set_tool_by_name("select")
        elif key == Qt.Key.Key_N and not event.isAutoRepeat():
            self.set_tool_by_name("node")
        elif key == Qt.Key.Key_H and not event.isAutoRepeat():
            if self._current_tool is not self._pan_tool:
                self._temp_pan_prev = self._current_tool
                self.set_tool(self._pan_tool)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                     Qt.Key.Key_Up,   Qt.Key.Key_Down):
            # Let the active tool handle arrow keys first (e.g. nudge selection).
            # Fall back to canvas scroll only if the tool doesn't consume the event.
            self._current_tool.key_press(event)
            if not event.isAccepted():
                sb_h = self.horizontalScrollBar()
                sb_v = self.verticalScrollBar()
                if key == Qt.Key.Key_Left:
                    sb_h.setValue(sb_h.value() - ARROW_KEY_SCROLL_PX)
                elif key == Qt.Key.Key_Right:
                    sb_h.setValue(sb_h.value() + ARROW_KEY_SCROLL_PX)
                elif key == Qt.Key.Key_Up:
                    sb_v.setValue(sb_v.value() - ARROW_KEY_SCROLL_PX)
                elif key == Qt.Key.Key_Down:
                    sb_v.setValue(sb_v.value() + ARROW_KEY_SCROLL_PX)
        elif key == Qt.Key.Key_Escape:
            self._current_tool.cancel()
        else:
            self._current_tool.key_press(event)
            if not event.isAccepted():
                super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_H and not event.isAutoRepeat():
            if self._temp_pan_prev is not None:
                self.set_tool(self._temp_pan_prev)
                self._temp_pan_prev = None
        else:
            super().keyReleaseEvent(event)

    def focusNextPrevChild(self, next: bool) -> bool:
        # Returning False prevents Qt from consuming Tab/Shift+Tab for widget
        # focus traversal, so those keys reach keyPressEvent instead.
        return False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_fit_done:
            self._initial_fit_done = True
            # Defer fit_page until the maximized window has its final size,
            # then grab keyboard focus so shortcuts work immediately.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._on_first_show)

    def _on_first_show(self):
        self.fit_page()
        self.setFocus()
