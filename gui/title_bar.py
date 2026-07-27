"""Custom title bar for the application window."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont

from gui.widgets import ShadowLabel


class CustomTitleBar(QWidget):
    """Custom title bar with window controls."""
    
    def __init__(self, parent=None):
        """Initialize custom title bar."""
        super().__init__(parent)
        self.parent_window = parent
        self.drag_position = QPoint()
        self.init_ui()
    
    def init_ui(self):
        """Initialize title bar UI."""
        self.setFixedHeight(32)
        self.setObjectName("customTitleBar")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)
        
        # Window title (will be styled by theme)
        self.title_label = ShadowLabel("FCC Collector")
        self.title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Window control buttons
        self.minimize_btn = QPushButton("−")
        self.minimize_btn.setObjectName("minimizeButton")
        self.minimize_btn.setFixedSize(32, 32)
        self.minimize_btn.setFont(QFont("Arial", 14))
        self.minimize_btn.clicked.connect(self.minimize_window)
        layout.addWidget(self.minimize_btn)
        
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeButton")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setFont(QFont("Arial", 18))
        self.close_btn.clicked.connect(self.close_window)
        layout.addWidget(self.close_btn)
    
    def minimize_window(self):
        """Minimize the window."""
        if self.parent_window:
            self.parent_window.showMinimized()
    
    def close_window(self):
        """Close the window."""
        if self.parent_window:
            self.parent_window.close()
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.drag_position:
                self.parent_window.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

