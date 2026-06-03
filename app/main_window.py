import os
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QStatusBar, QLabel, QFileDialog, QMessageBox,
)

from app.ruler import HRuler, VRuler, RULER_THICKNESS

from app.canvas import LaceCanvas
from app.toolbar import ToolBar
from app.tool_options_bar import ToolOptionsBar
from app.properties_panel import PropertiesPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bedfordshire Lace Designer")
        self.resize(1280, 820)
        self.setMinimumSize(800, 600)

        self._current_path = None
        self._dirty = False

        self._build_ui()
        self._build_menus()
        self._build_status_bar()
        self._connect_signals()
        self._update_title()

    # ── UI layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Tool options bar sits between menu bar and main content
        self._options_bar = ToolOptionsBar()

        # Main content row: toolbar | canvas-with-rulers | properties
        self._toolbar = ToolBar()
        self._canvas = LaceCanvas()
        self._props = PropertiesPanel()

        # Rulers + canvas in a 2×2 grid
        self._hrule = HRuler(self._canvas)
        self._vrule = VRuler(self._canvas)
        corner = QWidget()
        corner.setFixedSize(RULER_THICKNESS, RULER_THICKNESS)
        corner.setStyleSheet("background: #f0f0f0; border-right: 1px solid #b0b0b0; border-bottom: 1px solid #b0b0b0;")

        canvas_area = QWidget()
        cg = QGridLayout(canvas_area)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(0)
        cg.addWidget(corner,        0, 0)
        cg.addWidget(self._hrule,   0, 1)
        cg.addWidget(self._vrule,   1, 0)
        cg.addWidget(self._canvas,  1, 1)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._toolbar)
        content_layout.addWidget(canvas_area, stretch=1)
        content_layout.addWidget(self._props)

        # Outer vertical: options bar on top, content below
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._options_bar)
        outer_layout.addWidget(content, stretch=1)

        self.setCentralWidget(outer)

    # ── Menus ─────────────────────────────────────────────────────────────────

    def _build_menus(self):
        menu = self.menuBar()

        # File
        file_menu = menu.addMenu("&File")
        self._act_new = file_menu.addAction("&New")
        self._act_open = file_menu.addAction("&Open…")
        file_menu.addSeparator()
        self._act_save = file_menu.addAction("&Save")
        self._act_save_as = file_menu.addAction("Save &As…")
        file_menu.addSeparator()
        self._act_print = file_menu.addAction("&Print…")
        self._act_print.setShortcut(QKeySequence("Ctrl+P"))
        file_menu.addSeparator()
        self._act_export_pdf = file_menu.addAction("Export &PDF…")
        self._act_export_svg = file_menu.addAction("Export &SVG…")
        file_menu.addSeparator()
        act_quit = file_menu.addAction("&Quit")
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)

        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new.triggered.connect(self._on_new)
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        self._act_open.triggered.connect(self._on_open)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self._on_save)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._on_save_as)
        self._act_print.triggered.connect(self._canvas.print_page)
        self._act_export_pdf.triggered.connect(self._canvas.export_pdf)
        self._act_export_svg.triggered.connect(self._canvas.export_svg)

        # Edit
        edit_menu = menu.addMenu("&Edit")
        self._act_undo = edit_menu.addAction("&Undo")
        self._act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._act_redo = edit_menu.addAction("&Redo")
        self._act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        edit_menu.addSeparator()
        self._act_select_all = edit_menu.addAction("Select &All")
        self._act_select_all.setShortcut(QKeySequence("Ctrl+A"))

        self._act_select_all.setEnabled(False)

        # View
        view_menu = menu.addMenu("&View")
        act_zoom_in = view_menu.addAction("Zoom &In")
        act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        act_zoom_in.triggered.connect(self._canvas.zoom_in)

        act_zoom_out = view_menu.addAction("Zoom &Out")
        act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        act_zoom_out.triggered.connect(self._canvas.zoom_out)

        act_fit = view_menu.addAction("&Fit Page")
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.triggered.connect(self._canvas.fit_page)

        view_menu.addSeparator()
        self._act_grid = view_menu.addAction("&Grid")
        self._act_grid.setCheckable(True)
        self._act_grid.setEnabled(True)

        self._act_snap = view_menu.addAction("&Snap")
        self._act_snap.setCheckable(True)
        self._act_snap.setChecked(True)
        self._act_snap.setEnabled(False)

        # Help
        help_menu = menu.addMenu("&Help")
        act_about = help_menu.addAction("&About")
        act_about.triggered.connect(self._show_about)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._lbl_coords = QLabel("x: —  y: —")
        self._lbl_coords.setMinimumWidth(160)
        self._lbl_coords.setStyleSheet("font-size: 9pt; color: #505050;")

        self._lbl_zoom = QLabel("100%")
        self._lbl_zoom.setMinimumWidth(60)
        self._lbl_zoom.setStyleSheet("font-size: 9pt; color: #505050;")

        sb.addPermanentWidget(self._lbl_coords)
        sb.addPermanentWidget(self._lbl_zoom)

    # ── Signal connections ────────────────────────────────────────────────────

    def _connect_signals(self):
        self._toolbar.tool_selected.connect(self._on_tool_selected)
        self._canvas.cursor_moved.connect(self._on_cursor_moved)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)

        # Wire the trail pairs spinner → trail tool
        self._options_bar.trail_page().pairs_changed.connect(
            self._canvas.trail_tool().set_starting_pairs)

        # Wire the leaf tally ratio spinner → leaf tally tool
        self._options_bar.leaf_tally_page().ratio_changed.connect(
            self._canvas.leaf_tally_tool().set_ratio)

        # Keep toolbar buttons and options bar in sync with keyboard shortcuts
        self._canvas.tool_changed.connect(self._on_tool_changed_by_canvas)

        # Rulers — repaint on zoom, scroll, and cursor move
        self._canvas.zoom_changed.connect(lambda _: self._hrule.update())
        self._canvas.zoom_changed.connect(lambda _: self._vrule.update())
        self._canvas.horizontalScrollBar().valueChanged.connect(
            lambda _: self._hrule.update())
        self._canvas.verticalScrollBar().valueChanged.connect(
            lambda _: self._vrule.update())
        self._canvas.cursor_moved.connect(self._hrule.update_cursor)
        self._canvas.cursor_moved.connect(self._vrule.update_cursor)

        # Undo / Redo
        stack = self._canvas.undo_stack()
        self._act_undo.triggered.connect(stack.undo)
        self._act_redo.triggered.connect(stack.redo)
        self._act_undo.setEnabled(False)
        self._act_redo.setEnabled(False)
        stack.canUndoChanged.connect(self._act_undo.setEnabled)
        stack.canRedoChanged.connect(self._act_redo.setEnabled)

        # Grid toggle
        self._act_grid.toggled.connect(self._canvas.set_grid_visible)

        # Dirty flag — any undo stack change means the document was modified
        self._canvas.undo_stack().indexChanged.connect(self._on_document_changed)

    def _on_tool_selected(self, name: str):
        self._canvas.set_tool_by_name(name)
        self._options_bar.set_tool(name)

    def _on_tool_changed_by_canvas(self, name: str):
        """Sync toolbar button and options bar when tool changes via keyboard."""
        self._toolbar.set_active(name)
        self._options_bar.set_tool(name)

    def _on_cursor_moved(self, x_mm: float, y_mm: float):
        self._lbl_coords.setText(f"x: {x_mm:.1f} mm  y: {y_mm:.1f} mm")

    def _on_zoom_changed(self, zoom: float):
        self._lbl_zoom.setText(f"{zoom * 100:.0f}%")

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _update_title(self):
        name = os.path.basename(self._current_path) if self._current_path else "Untitled"
        dirty = " •" if self._dirty else ""
        self.setWindowTitle(f"{name}{dirty} — Bedfordshire Lace Designer")

    def _on_document_changed(self):
        self._dirty = True
        self._update_title()

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "The pattern has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    def _on_new(self):
        if not self._confirm_discard():
            return
        self._canvas.set_tool_by_name("select")
        self._canvas.clear()
        self._current_path = None
        self._dirty = False
        self._update_title()

    def _on_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Pattern", "", "Bedfordshire Lace patterns (*.blace)")
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self._canvas.set_tool_by_name("select")
            self._canvas.load_document(data)
            self._current_path = path
            self._dirty = False
            self._update_title()
        except Exception as e:
            QMessageBox.warning(self, "Open failed", f"Could not open file:\n{e}")

    def _on_save(self):
        if self._current_path:
            self._save_to(self._current_path)
        else:
            self._on_save_as()

    def _on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Pattern", "", "Bedfordshire Lace patterns (*.blace)")
        if not path:
            return
        if not path.endswith('.blace'):
            path += '.blace'
        self._save_to(path)

    def _save_to(self, path):
        try:
            data = self._canvas.dump_document()
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            self._current_path = path
            self._dirty = False
            self._update_title()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", f"Could not save file:\n{e}")

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
        else:
            event.accept()

    def _show_about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About Bedfordshire Lace Designer",
            "Bedfordshire Lace Designer\n\nA purpose-built tool for designing "
            "Bedfordshire bobbin lace pricking patterns.",
        )
