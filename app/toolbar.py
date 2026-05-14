from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QToolButton, QButtonGroup, QFrame,
)

# (tool_name, keyboard_shortcut_label, display_label, implemented)
TOOL_DEFINITIONS = [
    ("select",       "S",  "Select",        True),
    ("pan",          "H",  "Pan",           True),
    ("node",         "N",  "Node",          True),
    None,  # separator
    ("trail",        "T",  "Trail",         True),
    ("plait",        "P",  "Plait",         True),
    None,
    ("leaf_tally",   "L",  "Leaf\nTally",   True),
    ("rect_tally",   "R",  "Rect\nTally",   False),
    ("bud",          "B",  "Bud",           False),
    ("cloth_figure", "C",  "Cloth\nFigure", False),
    None,
    ("start_point",  ".",  "Start\nPoint",  False),
]


class _Separator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet("background: #cccccc; margin: 2px 4px;")


class ToolBar(QWidget):
    """Left vertical toolbar. Emits tool_selected(name) when a tool is clicked."""

    tool_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(56)
        self.setStyleSheet("""
            QToolButton {
                border: 1px solid #c0c0c0;
                border-radius: 3px;
                background: #f5f5f5;
                padding: 2px;
                font-size: 9pt;
            }
            QToolButton:checked {
                background: #c8ddf5;
                border-color: #4a80c0;
            }
            QToolButton:hover:!checked {
                background: #e8f0f8;
            }
            QToolButton:disabled {
                color: #b0b0b0;
                border-color: #ddd;
                background: #f8f8f8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        for item in TOOL_DEFINITIONS:
            if item is None:
                layout.addWidget(_Separator())
                continue

            tool_name, shortcut, label, implemented = item
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setFixedSize(48, 42)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if implemented:
                btn.setToolTip(f"{label.replace(chr(10), ' ')}  [{shortcut}]")
            else:
                btn.setToolTip(f"{label.replace(chr(10), ' ')} (coming soon)")
                btn.setEnabled(False)

            self._group.addButton(btn)
            self._buttons[tool_name] = btn
            layout.addWidget(btn)

            btn.toggled.connect(
                lambda checked, n=tool_name: checked and self.tool_selected.emit(n)
            )

        layout.addStretch()

        # Select is the default active tool
        self._buttons["select"].setChecked(True)

    def set_active(self, name: str):
        """Check the button for the given tool name (without emitting signal)."""
        btn = self._buttons.get(name)
        if btn and not btn.isChecked():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
