from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal


class _BlankPage(QWidget):
    """Empty page used for tools that have no options."""


class _TrailPage(QWidget):
    """Options bar content for the Trail tool."""

    pairs_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel(
            "Trail — click: add point  |  Shift+click: sharp corner  |  "
            "double-click: finish  |  click start point: close trail"))

        lbl = QLabel("Starting pairs:")
        lbl.setStyleSheet("color: #606060; font-size: 9pt;")
        layout.addWidget(lbl)

        self._spin = QSpinBox()
        self._spin.setRange(3, 30)
        self._spin.setValue(3)
        self._spin.setFixedWidth(48)
        self._spin.setToolTip("Number of pairs at the start of this trail")
        self._spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        layout.addWidget(self._spin)

        layout.addStretch()

        self._spin.valueChanged.connect(self.pairs_changed)

    def pairs(self) -> int:
        return self._spin.value()


class _LeafTallyPage(QWidget):
    """Options bar content for the Leaf Tally tool."""

    ratio_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel(
            "Leaf Tally — click: set first pin  |  drag: set angle and length  |  release: place"))

        lbl = QLabel("Width ratio:")
        lbl.setStyleSheet("color: #606060; font-size: 9pt;")
        layout.addWidget(lbl)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.05, 1.0)
        self._spin.setSingleStep(0.05)
        self._spin.setDecimals(2)
        self._spin.setValue(0.40)
        self._spin.setFixedWidth(60)
        self._spin.setToolTip(
            "Width as a proportion of length (0.40 = leaf is 40% as wide as it is long)")
        self._spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        layout.addWidget(self._spin)

        layout.addStretch()

        self._spin.valueChanged.connect(self.ratio_changed)

    def ratio(self) -> float:
        return self._spin.value()


class _PlaitPage(QWidget):
    """Options bar content for the Plait tool."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(QLabel(
            "Plait — click pinhole: start/end plait  |  "
            "click plait body: add/remove picot at nearest quarter-point"))
        layout.addStretch()


class _NodePage(QWidget):
    """Options bar content for the Node tool."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(QLabel(
            "Node — drag handle: move waypoint  |  "
            "click trail: insert waypoint  |  "
            "Shift+click handle: toggle cusp/smooth  |  "
            "Delete: remove waypoint"))
        layout.addStretch()


class ToolOptionsBar(QWidget):
    """
    Context-sensitive options bar shown below the menu bar.
    Uses a QStackedWidget to swap content when the active tool changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("background: #f0f0f0; border-bottom: 1px solid #d0d0d0;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # Index 0 — generic label page (select, pan, …)
        self._generic_page = QWidget()
        gl = QHBoxLayout(self._generic_page)
        gl.setContentsMargins(8, 0, 8, 0)
        self._label = QLabel("Select — click to select elements")
        self._label.setStyleSheet("color: #606060; font-size: 9pt;")
        gl.addWidget(self._label)
        gl.addStretch()
        self._stack.addWidget(self._generic_page)   # index 0

        # Index 1 — trail page
        self._trail_page = _TrailPage()
        self._stack.addWidget(self._trail_page)      # index 1

        # Index 2 — plait page
        self._plait_page = _PlaitPage()
        self._stack.addWidget(self._plait_page)      # index 2

        # Index 3 — leaf tally page
        self._leaf_tally_page = _LeafTallyPage()
        self._stack.addWidget(self._leaf_tally_page)  # index 3

        # Index 4 — node page
        self._node_page = _NodePage()
        self._stack.addWidget(self._node_page)        # index 4

        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------

    def set_tool(self, tool_name: str):
        """Update the bar when the active tool changes."""
        if tool_name == "trail":
            self._stack.setCurrentIndex(1)
            return
        if tool_name == "plait":
            self._stack.setCurrentIndex(2)
            return
        if tool_name == "leaf_tally":
            self._stack.setCurrentIndex(3)
            return
        if tool_name == "node":
            self._stack.setCurrentIndex(4)
            return

        self._stack.setCurrentIndex(0)
        labels = {
            "select": "Select — click: select  |  Tab: cycle all  |  Alt+click: cycle overlapping  |  Shift+click: add/remove  |  [ / ]: rotate 5°  |  Shift+[ / ]: rotate 45°  |  arrows: nudge  |  Shift+arrows: micro nudge  |  Ctrl+D: duplicate",
            "pan":    "Pan — drag to scroll the canvas  |  H: hold for temporary pan",
        }
        self._label.setText(
            labels.get(tool_name, tool_name.replace("_", " ").title()))

    def trail_page(self) -> _TrailPage:
        return self._trail_page

    def leaf_tally_page(self) -> _LeafTallyPage:
        return self._leaf_tally_page
