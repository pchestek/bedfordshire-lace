from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QSizePolicy,
)
from PySide6.QtCore import Qt


class _PlaceholderTab(QWidget):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet("color: #909090; font-size: 9pt; padding: 8px;")
        layout.addWidget(label)


class PropertiesPanel(QWidget):
    """
    Right-side panel with three tabs: Properties, Thread, Layers.
    Content is populated in later stages.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #fafafa; border-left: 1px solid #d0d0d0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab { padding: 5px 12px; font-size: 9pt; }
            QTabBar::tab:selected { border-bottom: 2px solid #4a80c0; }
        """)

        tabs.addTab(
            _PlaceholderTab("No element selected.\n\nSelect an element to view its properties."),
            "Properties",
        )
        tabs.addTab(
            _PlaceholderTab("Thread selection and pin spacing will appear here."),
            "Thread",
        )
        tabs.addTab(
            _PlaceholderTab("Layer visibility controls will appear here."),
            "Layers",
        )

        layout.addWidget(tabs)
