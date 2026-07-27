"""Main application window."""

import sys
import logging
import os
import platform
import html
from datetime import datetime, timedelta
from typing import List
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCalendarWidget, QMessageBox, QComboBox, QTableView, QLineEdit,
    QSpacerItem, QSizePolicy, QGraphicsOpacityEffect, QToolButton
)
from PyQt6.QtCore import Qt, QPoint, QDate, QRect, QPointF, QRectF, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QPixmap, QTextCharFormat, QColor, QPainter, QPen, QLinearGradient, QBrush, QPolygonF, QPainterPath

from gui.widgets import AnimatedProgressBar, ShadowLabel
from gui.title_bar import CustomTitleBar
from gui.themes import ThemeManager

# Import blur effect module (Windows only)
try:
    from .acrylic_blur import enable_blur, is_windows
    BLUR_AVAILABLE = is_windows()
except (ImportError, AttributeError):
    BLUR_AVAILABLE = False
    enable_blur = None
    is_windows = None
from core.collector import CollectionWorker
from utils.logger import setup_logger
from utils.config import OUTPUT_FOLDER_NAME, get_resource_path


class AdjacentMonthCalendar(QCalendarWidget):
    """
    Calendar widget with custom painting for:
      - muted previous/next month spillover dates
      - bright theme-colored selected/range dates

    QCalendarWidget.setDateTextFormat() and native selection visuals can be
    overridden by stylesheets, so selected/range cells are painted directly.
    """

    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self._normal_text_color = QColor("#ffffff")
        self._muted_text_color = QColor("#4f4f4f")
        self._cell_bg_color = QColor("#2b2b2b")
        self._grid_color = QColor("#555555")
        self._highlight_start_bg = QColor("#2f7d32")
        self._highlight_middle_bg = QColor("#3f9343")
        self._highlight_text_color = QColor("#ffffff")
        self._highlight_glass_top = QColor(255, 255, 255, 45)
        self._highlight_glass_bottom = QColor(255, 255, 255, 10)
        self._highlight_glass_border = QColor(255, 255, 255, 75)
        self._weekend_text_color = QColor("#ff0000")

    def set_calendar_colors(
        self,
        normal_text: QColor,
        muted_text: QColor,
        cell_bg: QColor,
        grid: QColor,
        highlight_start_bg: QColor = None,
        highlight_middle_bg: QColor = None,
        highlight_text: QColor = None,
        weekend_text: QColor = None,
    ):
        """Update paint colors used by the calendar."""
        self._normal_text_color = normal_text
        self._muted_text_color = muted_text
        self._cell_bg_color = cell_bg
        self._grid_color = grid

        if highlight_start_bg is not None:
            self._highlight_start_bg = QColor(highlight_start_bg)
        if highlight_middle_bg is not None:
            self._highlight_middle_bg = QColor(highlight_middle_bg)
        if highlight_text is not None:
            self._highlight_text_color = QColor(highlight_text)
        if weekend_text is not None:
            self._weekend_text_color = QColor(weekend_text)
        if highlight_start_bg is not None:
            base = QColor(highlight_start_bg)
            # Keep a soft "frosted" overlay that adapts to theme brightness.
            self._highlight_glass_top = QColor(255, 255, 255, 55 if base.lightness() < 160 else 40)
            self._highlight_glass_bottom = QColor(255, 255, 255, 16 if base.lightness() < 160 else 10)
            self._highlight_glass_border = QColor(255, 255, 255, 85 if base.lightness() < 160 else 65)

        # QCalendarWidget is not a QAbstractScrollArea, so it has no viewport().
        self.update()

    def _is_same_week(self, date1: QDate, date2: QDate) -> bool:
        """Return True if two dates are in the same calendar week."""
        if not date1.isValid() or not date2.isValid():
            return False
        week1, year1 = date1.weekNumber()
        week2, year2 = date2.weekNumber()
        return week1 == week2 and year1 == year2

    def _create_calendar_nav_icon(self, color: QColor, arrow_type: Qt.ArrowType, size: int = 16) -> QIcon:
        """Create a small pixmap-based navigation arrow icon in the theme color."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if arrow_type == Qt.ArrowType.LeftArrow:
            points = QPolygonF([
                QPointF(size * 0.65, size * 0.2),
                QPointF(size * 0.35, size * 0.5),
                QPointF(size * 0.65, size * 0.8),
            ])
        else:
            points = QPolygonF([
                QPointF(size * 0.35, size * 0.2),
                QPointF(size * 0.65, size * 0.5),
                QPointF(size * 0.35, size * 0.8),
            ])

        painter.drawPolygon(points)
        painter.end()

        return QIcon(pixmap)

    def _update_calendar_nav_arrows(self, theme: dict):
        """Assign theme-aware icons to the calendar's left/right navigation buttons."""
        arrow_color = QColor(theme.get('button_text', theme.get('text', '#ffffff')))
        icon_size = QSize(16, 16)
        prev_icon = self._create_calendar_nav_icon(arrow_color, Qt.ArrowType.LeftArrow, icon_size.width())
        next_icon = self._create_calendar_nav_icon(arrow_color, Qt.ArrowType.RightArrow, icon_size.width())

        for button in self.findChildren(QToolButton):
            try:
                name = button.objectName().lower()
                if 'prev' in name or 'previous' in name:
                    button.setIcon(prev_icon)
                    button.setIconSize(icon_size)
                elif 'next' in name:
                    button.setIcon(next_icon)
                    button.setIconSize(icon_size)
            except Exception:
                continue

    def _paint_glass_highlight(self, painter: QPainter, rect: QRect, bg: QColor, role: str, prev_connected: bool, next_connected: bool):
        """Paint a glass-like overlay while preserving the theme color."""
        highlight_rect = rect.adjusted(1, 2, -1, -2)
        glow_base = QColor(bg).lighter(170)
        radius = 4.0

        # If this cell connects with adjacent highlighted cells in the same week,
        # extend the highlight to the cell edge so the range looks continuous.
        if prev_connected:
            highlight_rect.setLeft(rect.left())
        if next_connected:
            highlight_rect.setRight(rect.right())

        painter.setPen(Qt.PenStyle.NoPen)
        if role == "middle":
            middle_bg = QColor(bg)
            middle_bg.setAlpha(172)
            painter.setBrush(middle_bg)
            painter.drawRect(QRectF(highlight_rect))
            top_alpha = min(145, int(self._highlight_glass_top.alpha() * 2.05))
            mid_alpha = 54
            bottom_alpha = min(70, int(self._highlight_glass_bottom.alpha() * 3.0))
            texture_alpha = 36
            border_alpha = min(165, int(self._highlight_glass_border.alpha() * 1.55))
            outer_glow_alpha = 132
            mid_glow_alpha = 96
            inner_glow_alpha = 64
        else:
            # Start/end/single date shapes should round only the exposed edges.
            path = QPainterPath()
            if role == "single" or (role == "start" and not next_connected) or (role == "end" and not prev_connected):
                path.addRoundedRect(QRectF(highlight_rect), radius, radius)
            elif role == "start":
                left = highlight_rect.left()
                top = highlight_rect.top()
                right = highlight_rect.right()
                bottom = highlight_rect.bottom()
                path.moveTo(right, top)
                path.lineTo(left + radius, top)
                path.quadTo(left, top, left, top + radius)
                path.lineTo(left, bottom - radius)
                path.quadTo(left, bottom, left + radius, bottom)
                path.lineTo(right, bottom)
                path.closeSubpath()
            elif role == "end":
                left = highlight_rect.left()
                top = highlight_rect.top()
                right = highlight_rect.right()
                bottom = highlight_rect.bottom()
                path.moveTo(left, top)
                path.lineTo(right - radius, top)
                path.quadTo(right, top, right, top + radius)
                path.lineTo(right, bottom - radius)
                path.quadTo(right, bottom, right - radius, bottom)
                path.lineTo(left, bottom)
                path.closeSubpath()
            else:
                path.addRect(QRectF(highlight_rect))

            painter.setBrush(bg)
            painter.drawPath(path)
            top_alpha = self._highlight_glass_top.alpha()
            mid_alpha = 22
            bottom_alpha = self._highlight_glass_bottom.alpha()
            texture_alpha = 12
            border_alpha = self._highlight_glass_border.alpha()
            outer_glow_alpha = 92
            mid_glow_alpha = 64
            inner_glow_alpha = 40

        # Theme-aware glow halo so highlights pop with each theme palette.
        glow_outer = QRect(highlight_rect).adjusted(-2, -2, 2, 2)
        glow_mid = QRect(highlight_rect).adjusted(-1, -1, 1, 1)
        glow_inner = QRect(highlight_rect).adjusted(0, 0, 0, 0)
        outer_pen = QPen(QColor(glow_base.red(), glow_base.green(), glow_base.blue(), outer_glow_alpha))
        outer_pen.setWidthF(1.0)
        mid_pen = QPen(QColor(glow_base.red(), glow_base.green(), glow_base.blue(), mid_glow_alpha))
        mid_pen.setWidthF(1.0)
        inner_pen = QPen(QColor(glow_base.red(), glow_base.green(), glow_base.blue(), inner_glow_alpha))
        inner_pen.setWidthF(1.0)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(glow_outer.adjusted(0, 0, -1, -1)), radius + 1.5, radius + 1.5)
        painter.setPen(mid_pen)
        painter.drawRoundedRect(QRectF(glow_mid.adjusted(0, 0, -1, -1)), radius + 0.8, radius + 0.8)
        painter.setPen(inner_pen)
        painter.drawRoundedRect(QRectF(glow_inner.adjusted(0, 0, -1, -1)), radius, radius)

        # Top-to-bottom translucent sheen for a light glass look.
        gradient = QLinearGradient(QPointF(highlight_rect.topLeft()), QPointF(highlight_rect.bottomLeft()))
        gradient.setColorAt(0.0, QColor(255, 255, 255, top_alpha))
        gradient.setColorAt(0.45, QColor(255, 255, 255, mid_alpha))
        gradient.setColorAt(1.0, QColor(255, 255, 255, bottom_alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        if role == "middle":
            painter.drawRect(QRectF(highlight_rect))
        else:
            painter.drawPath(path if 'path' in locals() else QPainterPath())

        # Very subtle texture to avoid a flat/solid block look.
        texture_brush = QBrush(QColor(255, 255, 255, texture_alpha), Qt.BrushStyle.Dense6Pattern)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(texture_brush)
        painter.drawRoundedRect(QRectF(highlight_rect.adjusted(1, 1, -1, -1)), max(3.5, radius - 1.3), max(3.5, radius - 1.3))

        # Crisp inner border to complete the translucent glass edge.
        glass_pen = QPen(QColor(255, 255, 255, border_alpha))
        glass_pen.setWidthF(1.0)
        painter.setPen(glass_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(highlight_rect.adjusted(0, 0, -1, -1)), max(3.5, radius - 0.7), max(3.5, radius - 0.7))

    def _date_role(self, date: QDate) -> str:
        """
        Return date role for current selected range.

        Possible values:
            "none", "single", "start", "middle", "end"
        """
        if self.owner is None or not getattr(self.owner, "start_date", None):
            return "none"

        py_date = date.toPyDate()
        start_date = self.owner.start_date
        end_date = self.owner.end_date

        if start_date and not end_date:
            return "single" if py_date == start_date else "none"

        if start_date and end_date:
            if py_date == start_date:
                return "start"
            if py_date == end_date:
                return "end"
            if start_date < py_date < end_date:
                return "middle"

        return "none"

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate):
        """
        Paint all date cells ourselves so the calendar grid stays thin/uniform.

        Qt stylesheets and QTableView grid lines can double-draw some cell
        borders. To avoid that, the table grid is disabled in apply_theme(),
        and this method draws exactly one 1px border per cell.
        """
        is_adjacent_month = (
            date.year() != self.yearShown()
            or date.month() != self.monthShown()
        )

        role = self._date_role(date)

        painter.save()

        # One consistent cell background and one consistent border.
        painter.fillRect(rect, self._cell_bg_color)

        # Draw grid lines fully inside the cell. A pen centered on x=0 can be
        # clipped by the QTableView viewport, which is why the far-left column
        # looked borderless. The 0.5px inset keeps 1px lines crisp and visible.
        pen = QPen(self._grid_color)
        pen.setWidthF(1.0)
        painter.setPen(pen)

        left = rect.left() + 0.5
        top = rect.top() + 0.5
        right = rect.right() - 0.5
        bottom = rect.bottom() - 0.5

        painter.drawLine(QPointF(left, top), QPointF(right, top))        # top
        painter.drawLine(QPointF(left, bottom), QPointF(right, bottom))  # bottom
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))      # left
        painter.drawLine(QPointF(right, top), QPointF(right, bottom))    # right

        # Adjacent-month spillover dates stay muted and never show selection bleed.
        if is_adjacent_month:
            text_color = self._muted_text_color
            bg = None
            prev_connected = False
            next_connected = False
        else:
            prev_date = date.addDays(-1)
            next_date = date.addDays(1)
            prev_connected = self._date_role(prev_date) != "none" and self._is_same_week(prev_date, date)
            next_connected = self._date_role(next_date) != "none" and self._is_same_week(next_date, date)

            if role != "none":
                bg = self._highlight_middle_bg if role == "middle" else self._highlight_start_bg
                text_color = self._highlight_text_color
            else:
                bg = None
                # Preserve the red weekend look used by the existing calendar.
                text_color = self._weekend_text_color if date.dayOfWeek() in (6, 7) else self._normal_text_color

        if bg is not None:
            # Keep a slim inset so the border remains visible and uniform.
            self._paint_glass_highlight(painter, rect, bg, role, prev_connected, next_connected)

        font = painter.font()
        font.setBold(role in {"single", "start", "end"})
        painter.setFont(font)

        painter.setPen(QPen(text_color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))

        painter.restore()


class FCC000CollectorApp(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        """Initialize main application window."""
        super().__init__()
        self.worker = None
        self.output_dir = None
        self.logger = None
        self.current_theme = "Default"
        self.themes = ThemeManager.get_themes()
        self.drag_position = QPoint()
        # Date range selection state
        self.start_date = None
        self.end_date = None
        self.date_selection_mode = "start"  # "start" or "end"
        self.highlighted_dates = set()  # Track highlighted dates for efficient clearing
        # Theme-specific header fonts (works in both dev and bundled exe)
        assets_dir = get_resource_path("assets")
        self.theme_fonts = {
            "Default": assets_dir / "aBigDeal.ttf",
            "Cyberpunk": assets_dir / "Sterion.ttf",
            "Kawaii": assets_dir / "MGF-PinlockPersonalUse.otf",
            "Coffee": assets_dir / "Baby_Coffee.otf",
        }
        self.theme_backgrounds = {
            "Cyberpunk": assets_dir / "theme_bg_cyberpunk_fallback.png",
            "Kawaii": assets_dir / "theme_bg_kawaii.png",
            "Coffee": assets_dir / "theme_bg_coffee.png",
        }
        self._active_wallpaper_theme = None
        self._active_wallpaper_source = QPixmap()
        
        self.setup_output_directory()
        self.setup_logging()
        self.init_ui()
        self._transition_animations = []
        
    def setup_output_directory(self):
        """Setup output directory in Downloads folder."""
        downloads_path = Path.home() / "Downloads"
        self.output_dir = downloads_path / OUTPUT_FOLDER_NAME
        self.output_dir.mkdir(exist_ok=True)
    
    def setup_logging(self):
        """Setup logging system."""
        # Only console logging here - file logging is handled in run-specific folders
        self.logger = setup_logger(include_file_handler=False)
        self.logger.info(f"Output directory: {self.output_dir}")
    
    def init_ui(self):
        """Initialize user interface."""
        # Set application icon (works in both dev and bundled exe)
        assets_dir = get_resource_path("assets")
        icon_path = assets_dir / "fcc_bg.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Remove default window frame for custom title bar
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("FCC Collector")
        self.setGeometry(100, 100, 420, 430)  # Trimmed vertical space for tighter idle layout
        self.setFixedSize(420, 430)  # Keep deterministic framing for both UI states
        
        # Track blur state
        self._blur_enabled = False
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.theme_wallpaper_label = QLabel(central_widget)
        self.theme_wallpaper_label.setObjectName("themeWallpaperLabel")
        self.theme_wallpaper_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.theme_wallpaper_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.theme_wallpaper_label.hide()
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Custom title bar
        self.title_bar = CustomTitleBar(self)
        layout.addWidget(self.title_bar)

        # Content widget (make it draggable)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        content_layout = QVBoxLayout(self.content_widget)
        self.content_layout = content_layout
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.content_widget)
        
        # Top row: Theme dropdown (left) and View Folder button (right)
        top_row = QHBoxLayout()
        
        # Theme dropdown on the left
        self.theme_label = ShadowLabel("Theme:")
        self.theme_label.setFont(QFont("Arial", 8))
        top_row.addWidget(self.theme_label)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(self.themes.keys()))
        self.theme_combo.setCurrentText(self.current_theme)
        self.theme_combo.setFixedWidth(120)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        top_row.addWidget(self.theme_combo)
        
        top_row.addStretch()  # Push button to the right
        
        # View Folder button on the right
        self.view_folder_button = QPushButton("View Folder")
        self.view_folder_button.setObjectName("viewFolderButton")
        self.view_folder_button.setFont(QFont("Arial", 8))
        self.view_folder_button.setFixedWidth(100)  # Compact size
        self.view_folder_button.clicked.connect(self.open_collections_folder)
        top_row.addWidget(self.view_folder_button)
        
        content_layout.addLayout(top_row)

        # Automation-only date display shown inside the running status stack.
        self.automation_date_section = QWidget()
        automation_date_layout = QHBoxLayout(self.automation_date_section)
        automation_date_layout.setContentsMargins(0, 0, 0, 0)
        automation_date_layout.setSpacing(0)
        automation_date_layout.addStretch()
        self.automation_date_label = QLabel()
        self.automation_date_label.setFont(QFont("Arial", 8))
        self.automation_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.automation_date_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        automation_date_layout.addWidget(self.automation_date_label)
        automation_date_layout.addStretch()
        self.automation_date_section.setVisible(False)
        
        # Calendar section (hidden during automation mode)
        self.calendar_section = QWidget()
        calendar_section_layout = QVBoxLayout(self.calendar_section)
        calendar_section_layout.setSpacing(8)
        calendar_section_layout.setContentsMargins(0, 0, 0, 0)

        # Calendar widget with date range selection
        self.calendar_label = ShadowLabel("Select Date/s:")
        self.calendar_label.setFont(QFont("Arial", 9))
        calendar_section_layout.addWidget(self.calendar_label)
        
        self.calendar = AdjacentMonthCalendar(self)
        self.calendar.setGridVisible(False)
        # Default to yesterday's date (site updates 24 hours late, so today is invalid)
        self.calendar.setSelectedDate((datetime.now().date() - timedelta(days=1)))
        # Hide week number column to save space
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        # Set fixed size for calendar - reduced height to prevent overlap
        self.calendar.setFixedSize(390, 180)
        # Connect calendar clicks to handle date range.
        # Keep selection enabled so the calendar remains clickable, but suppress
        # the native selected-cell paint via stylesheet in apply_theme().
        # Manual range highlighting is handled by _highlight_date_range().
        self.calendar.setSelectionMode(QCalendarWidget.SelectionMode.SingleSelection)
        self.calendar.clicked.connect(self.on_calendar_date_clicked)
        self.calendar.currentPageChanged.connect(self.on_calendar_page_changed)

        # Center the calendar horizontally within the main layout
        calendar_row = QHBoxLayout()
        calendar_row.addStretch()
        calendar_row.addWidget(self.calendar)
        calendar_row.addStretch()
        calendar_section_layout.addLayout(calendar_row)
        content_layout.addWidget(self.calendar_section)

        # Controls section (centered during automation mode)
        self.controls_section = QWidget()
        controls_layout = QVBoxLayout(self.controls_section)
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Date range input fields (editable)
        self.date_range_layout = QHBoxLayout()
        self.date_range_layout.addStretch()  # For centering during automation
        
        # Start date label and input
        self.start_label = ShadowLabel("Start Date:")
        self.start_label.setFont(QFont("Arial", 8))
        self.date_range_layout.addWidget(self.start_label)
        
        self.start_date_input = QLineEdit()
        self.start_date_input.setFont(QFont("Arial", 8))
        self.start_date_input.setPlaceholderText("Any format (e.g., 2026-02-18, 02/18/2026)")
        self.start_date_input.setToolTip("Enter date in any common format:\n• YYYY-MM-DD (2026-02-18)\n• MM/DD/YYYY (02/18/2026)\n• MMDDYYYY (02182026)\nOr click on calendar")
        self.start_date_input.textChanged.connect(self.on_start_date_text_changed)
        self.start_date_input.editingFinished.connect(self.validate_start_date)
        self.date_range_layout.addWidget(self.start_date_input)
        
        # Start date display label (shown during automation)
        self.start_date_label = QLabel()
        self.start_date_label.setFont(QFont("Arial", 8))
        self.start_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_date_label.setVisible(False)  # Hidden initially
        self.start_date_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.date_range_layout.addWidget(self.start_date_label)
        
        # End date label and input
        self.end_label = ShadowLabel("End Date:")
        self.end_label.setFont(QFont("Arial", 8))
        self.date_range_layout.addWidget(self.end_label)
        
        self.end_date_input = QLineEdit()
        self.end_date_input.setFont(QFont("Arial", 8))
        self.end_date_input.setPlaceholderText("Any format (e.g., 2026-02-18, 02/18/2026)")
        self.end_date_input.setToolTip("Enter date in any common format:\n• YYYY-MM-DD (2026-02-18)\n• MM/DD/YYYY (02/18/2026)\n• MMDDYYYY (02182026)\nOr click on calendar")
        self.end_date_input.textChanged.connect(self.on_end_date_text_changed)
        self.end_date_input.editingFinished.connect(self.validate_end_date)
        self.date_range_layout.addWidget(self.end_date_input)
        
        # End date display label (shown during automation)
        self.end_date_label = QLabel()
        self.end_date_label.setFont(QFont("Arial", 8))
        self.end_date_label.setFixedWidth(70)  # Compact width for date display
        self.end_date_label.setVisible(False)  # Hidden initially
        self.date_range_layout.addWidget(self.end_date_label)
        
        # Clear selection button
        self.clear_dates_button = QPushButton("Clear")
        self.clear_dates_button.setFont(QFont("Arial", 8))
        self.clear_dates_button.setFixedWidth(50)
        self.clear_dates_button.clicked.connect(self.reset_date_selection)
        self.date_range_layout.addWidget(self.clear_dates_button)
        self.date_range_layout.addStretch()  # For centering during automation
        
        controls_layout.addLayout(self.date_range_layout)
        controls_layout.addWidget(self.automation_date_section)
        self.progress_bar_spacer = QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        controls_layout.addItem(self.progress_bar_spacer)
        
        # Collect button (will be replaced by STOP button during automation)
        self.collect_button = QPushButton("Collect")
        self.collect_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.collect_button.clicked.connect(self.start_collection)
        controls_layout.addWidget(self.collect_button)
        
        # STOP button (hidden initially, shown during automation)
        self.stop_button = QPushButton("STOP")
        self.stop_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.stop_button.setFixedWidth(80)  # Make it more compact
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_collection)
        self.stop_button.setVisible(False)  # Hidden initially
        # Note: stop_button is now added to bottom_section, not controls_layout
        
        # Progress bar
        self.progress_bar = AnimatedProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        controls_layout.addWidget(self.progress_bar)
        
        # Status label (at the bottom)
        self.status_label = QLabel("Ready.")
        self.status_label.setFont(QFont("Arial", 8))
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        controls_layout.addWidget(self.status_label)
        self.stop_button_spacer = QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        controls_layout.addItem(self.stop_button_spacer)

        # Bottom section for stop button during automation
        self.bottom_section = QWidget()
        self.bottom_section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        bottom_layout = QHBoxLayout(self.bottom_section)
        bottom_layout.setContentsMargins(0, 0, 0, 4)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.stop_button)
        bottom_layout.addStretch()
        self.bottom_section.setVisible(False)  # Hidden initially
        controls_layout.addWidget(self.bottom_section)

        # Dynamic spacers to center controls while automation runs.
        self._automation_top_spacer = QSpacerItem(
            20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self._automation_bottom_spacer = QSpacerItem(
            20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        content_layout.addItem(self._automation_top_spacer)
        content_layout.addWidget(self.controls_section)
        content_layout.addItem(self._automation_bottom_spacer)

        # Opacity effects used by idle/running state transitions.
        self._calendar_opacity = QGraphicsOpacityEffect(self.calendar_section)
        self._calendar_opacity.setOpacity(1.0)
        self.calendar_section.setGraphicsEffect(self._calendar_opacity)

        self._controls_opacity = QGraphicsOpacityEffect(self.controls_section)
        self._controls_opacity.setOpacity(1.0)
        self.controls_section.setGraphicsEffect(self._controls_opacity)
        
        # Apply default theme
        self.apply_theme(self.current_theme)
        self._set_running_ui_state(False)
        
        # Style adjacent month dates initially
        self._style_calendar_adjacent_dates()
        
        # Set default start date to yesterday (so user can immediately click Collect)
        yesterday = datetime.now().date() - timedelta(days=1)
        self.start_date = yesterday
        self.start_date_input.setText(yesterday.strftime('%Y-%m-%d'))
        self.calendar.setSelectedDate(QDate(yesterday.year, yesterday.month, yesterday.day))
        self._update_date_input_styles()
        self._update_date_display_labels()
        self._highlight_date_range()
        self.status_label.setText(f"Single date selected: {yesterday.strftime('%Y-%m-%d')}")

    def _set_running_ui_state(self, is_running: bool):
        """
        Switch between idle and automation-focused layouts.

        Idle:
            - Calendar visible
            - Progress bar hidden
        Running:
            - Calendar hidden
            - Controls section vertically centered
            - Progress bar shown
        """
        if not hasattr(self, "calendar_section") or not hasattr(self, "progress_bar"):
            return

        self.automation_date_section.setVisible(is_running)
        self.calendar_section.setVisible(not is_running)
        self.progress_bar.setVisible(is_running)
        self.bottom_section.setVisible(is_running)

        # Toggle date input fields vs display labels
        if is_running:
            self.start_label.setVisible(False)
            self.end_label.setVisible(False)
            self.start_date_input.setVisible(False)
            self.end_date_input.setVisible(False)
            self.start_date_label.setVisible(False)
            self.end_date_label.setVisible(False)  # Hide end date label since dates are combined
            self.clear_dates_button.setVisible(False)
            self.date_range_layout.setSpacing(0)  # Very tight spacing during automation
            self._update_date_display_labels()
            self.progress_bar_spacer.changeSize(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self.stop_button_spacer.changeSize(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        else:
            self.start_label.setVisible(True)
            self.end_label.setVisible(True)
            self.start_date_input.setVisible(True)
            self.end_date_input.setVisible(True)
            self.start_date_label.setVisible(False)
            self.end_date_label.setVisible(False)
            self.clear_dates_button.setVisible(True)
            self.date_range_layout.setSpacing(6)  # Normal spacing during idle
            self.progress_bar_spacer.changeSize(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self.stop_button_spacer.changeSize(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        if is_running:
            self._automation_top_spacer.changeSize(
                20, 70, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
            self._automation_bottom_spacer.changeSize(
                20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
            # Keep the stop button position fixed while lowering the other automation elements.
            if hasattr(self, "content_layout") and self.content_layout is not None:
                self.content_layout.setStretch(0, 0)
                self.content_layout.setStretch(1, 0)
                self.content_layout.setStretch(2, 0)
                self.content_layout.setStretch(3, 1)
                self.content_layout.setStretch(4, 0)

        else:
            # Keep idle mode visually higher by placing flexible space below
            # the full calendar + controls block (not between sections).
            self._automation_top_spacer.changeSize(
                20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
            self._automation_bottom_spacer.changeSize(
                20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
            )
            if hasattr(self, "content_layout") and self.content_layout is not None:
                self.content_layout.setStretch(0, 0)
                self.content_layout.setStretch(1, 0)
                self.content_layout.setStretch(2, 0)
                self.content_layout.setStretch(3, 0)
                self.content_layout.setStretch(4, 1)

        if hasattr(self, "content_layout") and self.content_layout is not None:
            self.content_layout.invalidate()
        if hasattr(self, "content_widget") and self.content_widget is not None:
            self.content_widget.updateGeometry()
            self.content_widget.update()

    def _stop_transition_animations(self):
        """Stop and clear any currently running UI transition animations."""
        for animation in self._transition_animations:
            try:
                animation.stop()
            except Exception:
                pass
        self._transition_animations.clear()

    def _animate_opacity(self, effect: QGraphicsOpacityEffect, start: float, end: float, duration_ms: int):
        """Create and start a lightweight opacity animation."""
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration_ms)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._transition_animations.append(animation)

        def _cleanup():
            if animation in self._transition_animations:
                self._transition_animations.remove(animation)

        animation.finished.connect(_cleanup)
        animation.start()
        return animation

    def _transition_to_running_state(self):
        """Softly fade from idle layout into running layout."""
        self._stop_transition_animations()

        if not self.calendar_section.isVisible():
            self._set_running_ui_state(True)
            self._controls_opacity.setOpacity(1.0)
            return

        calendar_fade = self._animate_opacity(
            self._calendar_opacity, self._calendar_opacity.opacity(), 0.0, 210
        )

        def _show_running():
            self._set_running_ui_state(True)
            self._controls_opacity.setOpacity(0.86)
            self._animate_opacity(self._controls_opacity, 0.86, 1.0, 250)

        calendar_fade.finished.connect(_show_running)

    def _transition_to_idle_state(self):
        """Softly fade from running layout back to idle layout."""
        self._stop_transition_animations()

        if self.calendar_section.isVisible():
            self._set_running_ui_state(False)
            self._calendar_opacity.setOpacity(1.0)
            return

        controls_fade = self._animate_opacity(
            self._controls_opacity, self._controls_opacity.opacity(), 0.82, 180
        )

        def _show_idle():
            self._set_running_ui_state(False)
            self._controls_opacity.setOpacity(1.0)
            self._calendar_opacity.setOpacity(0.0)
            self._animate_opacity(self._calendar_opacity, 0.0, 1.0, 270)

        controls_fade.finished.connect(_show_idle)
    

    def on_calendar_date_clicked(self, qdate: QDate):
        """Handle calendar date clicks for range selection without native selection bleed."""
        selected_date = qdate.toPyDate()

        if self.date_selection_mode == "start":
            # First click: set start date
            self.start_date = selected_date
            self.end_date = None
            self.start_date_input.setText(selected_date.strftime("%Y-%m-%d"))
            self.end_date_input.clear()
            self.date_selection_mode = "end"
            self.status_label.setText(
                f"Start date selected: {selected_date.strftime('%Y-%m-%d')}. "
                "Click again for end date (or leave empty for single date)."
            )
        else:
            # Second click: set end date
            self.end_date = selected_date
            self.end_date_input.setText(selected_date.strftime("%Y-%m-%d"))
            self.date_selection_mode = "start"

            if self.start_date:
                if self.start_date <= self.end_date:
                    if self.start_date == self.end_date:
                        self.status_label.setText(
                            f"Single date selected: {self.start_date.strftime('%Y-%m-%d')}"
                        )
                    else:
                        self.status_label.setText(
                            f"Date range: {self.start_date.strftime('%Y-%m-%d')} "
                            f"to {self.end_date.strftime('%Y-%m-%d')}"
                        )
                else:
                    self.status_label.setText("Warning: End date is before start date. Please adjust.")

        self._update_date_input_styles()
        self._update_date_display_labels()
        self._style_calendar_adjacent_dates()
        self._highlight_date_range()

    def on_calendar_selection_changed(self):
        """Handle calendar date selection for range selection."""
        selected_date = self.calendar.selectedDate().toPyDate()
        
        if self.date_selection_mode == "start":
            # First click: set start date
            self.start_date = selected_date
            self.end_date = None  # Clear end date if selecting new start
            self.start_date_input.setText(selected_date.strftime('%Y-%m-%d'))
            self.end_date_input.clear()
            self.date_selection_mode = "end"
            self.status_label.setText(f"Start date selected: {selected_date.strftime('%Y-%m-%d')}. Click again for end date (or leave empty for single date).")
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()  # Highlight just the start date
        else:
            # Second click: set end date
            self.end_date = selected_date
            self.end_date_input.setText(selected_date.strftime('%Y-%m-%d'))
            self.date_selection_mode = "start"  # Reset for next selection
            if self.start_date:
                if self.start_date <= self.end_date:
                    if self.start_date == self.end_date:
                        self.status_label.setText(f"Single date selected: {self.start_date.strftime('%Y-%m-%d')}")
                    else:
                        self.status_label.setText(f"Date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
                else:
                    self.status_label.setText("Warning: End date is before start date. Please adjust.")
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()  # Highlight the full range
    
    def on_calendar_page_changed(self):
        """Handle calendar month/year page change to reapply adjacent date styling."""
        self._style_calendar_adjacent_dates()
    
    def parse_date_string(self, date_str: str):
        """Parse date string in various formats and return date object or None."""
        if not date_str or not date_str.strip():
            return None
        
        date_str = date_str.strip()
        
        # Try common date formats (order matters - try more specific first)
        formats = [
            '%Y-%m-%d',      # 2026-02-18
            '%Y/%m/%d',      # 2026/02/18
            '%m-%d-%Y',      # 02-18-2026
            '%m/%d/%Y',      # 02/18/2026
            '%d-%m-%Y',      # 18-02-2026
            '%d/%m/%Y',      # 18/02/2026
            '%Y%m%d',        # 20260218 (no separators)
            '%m%d%Y',        # 02182026 (no separators)
            '%d%m%Y',        # 18022026 (no separators)
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def on_start_date_text_changed(self, text: str):
        """Handle start date text input changes."""
        # Don't update if user is still typing
        pass
    
    def validate_start_date(self):
        """Validate and set start date from text input."""
        text = self.start_date_input.text().strip()
        if not text:
            self.start_date = None
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()
            return
        
        parsed_date = self.parse_date_string(text)
        if parsed_date:
            self.start_date = parsed_date
            # Update calendar selection
            self.calendar.setSelectedDate(QDate(parsed_date.year, parsed_date.month, parsed_date.day))
            self.date_selection_mode = "end"  # Ready for end date selection
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()
            if self.end_date:
                # Re-validate range if end date exists
                if self.start_date <= self.end_date:
                    if self.start_date == self.end_date:
                        self.status_label.setText(f"Single date selected: {self.start_date.strftime('%Y-%m-%d')}")
                    else:
                        self.status_label.setText(f"Date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
                else:
                    self.status_label.setText("Warning: End date is before start date. Please adjust.")
            else:
                # Single date selected (no end date)
                self.status_label.setText(f"Single date selected: {self.start_date.strftime('%Y-%m-%d')}")
        else:
            # Invalid date format - show error but keep theme styling
            theme = self.themes.get(self.current_theme, self.themes["Default"])
            window_bg = theme.get('window_bg', '#2b2b2b')
            progress_border = theme.get('progress_border', '#555555')
            error_style = f"""
                QLineEdit {{
                    background-color: {window_bg};
                    color: #ff4444;
                    border: 2px solid #ff4444;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """
            self.start_date_input.setStyleSheet(error_style)
            self.status_label.setText(f"Invalid date format: {text}. Try: YYYY-MM-DD, MM/DD/YYYY, MMDDYYYY, etc.")
    
    def on_end_date_text_changed(self, text: str):
        """Handle end date text input changes."""
        # Don't update if user is still typing
        pass
    
    def validate_end_date(self):
        """Validate and set end date from text input."""
        text = self.end_date_input.text().strip()
        if not text:
            self.end_date = None
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()
            return
        
        parsed_date = self.parse_date_string(text)
        if parsed_date:
            self.end_date = parsed_date
            # Update calendar selection
            self.calendar.setSelectedDate(QDate(parsed_date.year, parsed_date.month, parsed_date.day))
            self.date_selection_mode = "start"  # Reset for next selection
            self._update_date_input_styles()
            self._update_date_display_labels()
            self._highlight_date_range()
            if self.start_date:
                if self.start_date <= self.end_date:
                    if self.start_date == self.end_date:
                        self.status_label.setText(f"Single date selected: {self.start_date.strftime('%Y-%m-%d')}")
                    else:
                        self.status_label.setText(f"Date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
                else:
                    self.status_label.setText("Warning: End date is before start date. Please adjust.")
        else:
            # Invalid date format - show error but keep theme styling
            theme = self.themes.get(self.current_theme, self.themes["Default"])
            window_bg = theme.get('window_bg', '#2b2b2b')
            progress_border = theme.get('progress_border', '#555555')
            error_style = f"""
                QLineEdit {{
                    background-color: {window_bg};
                    color: #ff4444;
                    border: 2px solid #ff4444;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """
            self.end_date_input.setStyleSheet(error_style)
            self.status_label.setText(f"Invalid date format: {text}. Try: YYYY-MM-DD, MM/DD/YYYY, MMDDYYYY, etc.")
    
    def get_selected_date_range(self) -> List[str]:
        """Get selected date range as list of YYYY/MM/DD format strings."""
        # Single date selection: if only start_date is set, or both are the same
        if self.start_date and not self.end_date:
            return [self.start_date.strftime("%Y/%m/%d")]
        
        if not self.start_date:
            return []
        
        # If end_date is set, use it (even if same as start_date for range of 1)
        if self.end_date:
            dates = []
            current_date = self.start_date
            while current_date <= self.end_date:
                dates.append(current_date.strftime("%Y/%m/%d"))
                current_date += timedelta(days=1)
            return dates
        
        return []
    
    def reset_date_selection(self):
        """Reset date range selection."""
        self.start_date = None
        self.end_date = None
        self.date_selection_mode = "start"
        self.start_date_input.clear()
        self.end_date_input.clear()
        # Reset to yesterday's date
        self.calendar.setSelectedDate((datetime.now().date() - timedelta(days=1)))
        self.status_label.setText("Ready. Click calendar or type dates (YYYY-MM-DD) to select range.")
        # Update input styles based on current theme
        self._update_date_input_styles()
        self._update_date_display_labels()
        # Clear calendar highlights
        self._clear_calendar_highlights()
    
    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color string to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _lighten_color(self, rgb: tuple, factor: float = 0.3) -> tuple:
        """Lighten an RGB color by a factor (0-1)."""
        r, g, b = rgb
        # Increase brightness by adding white
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return (r, g, b)
    
    def _is_dark_color(self, rgb: tuple) -> bool:
        """Check if a color is dark (needs light text)."""
        # Calculate luminance
        r, g, b = rgb
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5
    
    def _get_theme_highlight_colors(self):
        """
        Get calendar range-highlight colors based on the current theme.

        The base highlight follows the theme's Collect button color
        (theme["primary"]), then uses a darker shade so date text remains
        readable and the highlight does not overpower the calendar.
        """
        theme = self.themes.get(self.current_theme, self.themes["Default"])

        primary_hex = theme.get("primary", "#4CAF50")
        primary = QColor(primary_hex)

        # QColor.darker(100) is unchanged; higher values are darker.
        start_bg = primary.darker(135)
        middle_bg = primary.darker(118)

        bright_text = QColor(255, 255, 255)

        return {
            "start_bg": start_bg,
            "start_text": bright_text,
            "end_bg": QColor(start_bg),
            "end_text": bright_text,
            "middle_bg": middle_bg,
            "middle_text": bright_text,
        }


    def _highlight_date_range(self):
        """
        Track the selected date/range and repaint the calendar.

        The actual visible highlight is painted by AdjacentMonthCalendar.paintCell()
        so it cannot be muted/overridden by QTableView stylesheet rules.
        """
        self.highlighted_dates.clear()

        if not self.start_date:
            self.calendar.update()
            return

        if self.start_date and not self.end_date:
            self.highlighted_dates.add(
                (self.start_date.year, self.start_date.month, self.start_date.day)
            )

        elif self.start_date and self.end_date:
            current_date = self.start_date
            while current_date <= self.end_date:
                self.highlighted_dates.add(
                    (current_date.year, current_date.month, current_date.day)
                )
                current_date += timedelta(days=1)

        self.calendar.update()

    def _clear_previous_highlights(self):
        """Clear tracked highlighted dates and repaint the calendar."""
        self.highlighted_dates.clear()
        if hasattr(self, "calendar") and self.calendar is not None:
            self.calendar.update()

    def _clear_calendar_highlights(self):
        """Clear all date highlights from the calendar (used for reset)."""
        # Only clear tracked dates for efficiency
        self._clear_previous_highlights()
    
    def _style_calendar_adjacent_dates(self):
        """
        Style previous/next month dates with visibly lower contrast.

        This uses AdjacentMonthCalendar.paintCell(), because stylesheet rules can
        override QCalendarWidget.setDateTextFormat() foreground colors.
        """
        if not hasattr(self, "calendar") or self.calendar is None:
            return

        try:
            theme = self.themes.get(self.current_theme, self.themes["Default"])

            normal_color = QColor(theme.get("text", "#ffffff"))
            cell_bg = QColor(theme.get("window_bg", "#2b2b2b"))
            grid_color = QColor(theme.get("progress_border", "#555555"))

            muted_colors = {
                "Default": "#4f4f4f",
                "Cyberpunk": "#004747",
                "Kawaii": "#9a86a8",
                "Coffee": "#6f6255",
            }
            muted_color = QColor(muted_colors.get(self.current_theme, "#4f4f4f"))

            if hasattr(self.calendar, "set_calendar_colors"):
                highlight_colors = self._get_theme_highlight_colors()
                self.calendar.set_calendar_colors(
                    normal_text=normal_color,
                    muted_text=muted_color,
                    cell_bg=cell_bg,
                    grid=grid_color,
                    highlight_start_bg=highlight_colors["start_bg"],
                    highlight_middle_bg=highlight_colors["middle_bg"],
                    highlight_text=highlight_colors["start_text"],
                    weekend_text=QColor("#ff0000"),
                )

            # Keep selected-date/range highlights on top of normal calendar formatting.
            if self.start_date or self.end_date:
                self._highlight_date_range()

            self.calendar.update()

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not style calendar adjacent dates: {e}")

    def _update_date_input_styles(self):
        """Update date input field styles based on current theme."""
        theme = self.themes.get(self.current_theme, self.themes["Default"])
        primary_color = theme.get('primary', '#4CAF50')
        text_secondary = theme.get('text_secondary', '#888')
        window_bg = theme.get('window_bg', '#2b2b2b')
        progress_border = theme.get('progress_border', '#555555')
        
        # Base style for input fields
        base_style = f"""
            QLineEdit {{
                background-color: {window_bg};
                color: {theme.get('text', '#ffffff')};
                border: 1px solid {progress_border};
                border-radius: 4px;
                padding: 4px;
            }}
            QLineEdit:focus {{
                border: 2px solid {primary_color};
            }}
        """
        
        # Start date input
        if self.start_date:
            start_style = base_style + f"QLineEdit {{ color: {primary_color}; font-weight: bold; }}"
            self.start_date_input.setStyleSheet(start_style)
        else:
            self.start_date_input.setStyleSheet(base_style + f"QLineEdit {{ color: {text_secondary}; }}")
        
        # End date input
        if self.end_date:
            end_style = base_style + f"QLineEdit {{ color: {primary_color}; font-weight: bold; }}"
            self.end_date_input.setStyleSheet(end_style)
        else:
            self.end_date_input.setStyleSheet(base_style + f"QLineEdit {{ color: {text_secondary}; }}")
    
    def _update_date_display_labels(self):
        """Update the date display labels with current dates."""
        # Apply styling to labels similar to inputs
        theme = self.themes.get(self.current_theme, self.themes["Default"])
        primary_color = theme.get('primary', '#4CAF50')
        text_secondary = theme.get('text_secondary', '#888')

        if self.start_date and self.end_date:
            # Keep a compact legacy label for layout compatibility and a
            # metadata-style label for the automation status stack.
            formatted_start = self.start_date.strftime('%m/%d/%Y')
            formatted_end = self.end_date.strftime('%m/%d/%Y')
            start_date_text = (
                f"<span style='color: {primary_color}; font-weight: bold;'>{formatted_start}</span>&nbsp;&nbsp;"
                f"<span style='color: {theme.get('text', '#ffffff')};'>to</span>&nbsp;&nbsp;"
                f"<span style='color: {primary_color}; font-weight: bold;'>{formatted_end}</span>"
            )
            automation_text = (
                f"<span style='color: {text_secondary}; font-weight: 600;'>Date Range:</span>&nbsp;"
                f"<span style='color: {primary_color}; font-weight: bold;'>{formatted_start}</span>&nbsp;"
                f"<span style='color: {text_secondary};'>to</span>&nbsp;"
                f"<span style='color: {primary_color}; font-weight: bold;'>{formatted_end}</span>"
            )
            self.start_date_label.setText(start_date_text)
            self.start_date_label.setTextFormat(Qt.TextFormat.RichText)
            self.start_date_label.setStyleSheet("")
            self.automation_date_label.setText(automation_text)
            self.automation_date_label.setTextFormat(Qt.TextFormat.RichText)
            self.automation_date_label.setStyleSheet("")
            self.end_date_label.setText("")
        elif self.start_date:
            single_date_text = self.start_date.strftime('%m/%d/%Y')
            self.start_date_label.setText(single_date_text)
            self.start_date_label.setTextFormat(Qt.TextFormat.AutoText)
            self.start_date_label.setStyleSheet(f"color: {primary_color}; font-weight: bold;")
            self.automation_date_label.setText(
                f"<span style='color: {text_secondary}; font-weight: 600;'>Date:</span>&nbsp;"
                f"<span style='color: {primary_color}; font-weight: bold;'>{single_date_text}</span>"
            )
            self.automation_date_label.setTextFormat(Qt.TextFormat.RichText)
            self.automation_date_label.setStyleSheet("")
            self.end_date_label.setText("")
        else:
            self.start_date_label.setText("")
            self.start_date_label.setTextFormat(Qt.TextFormat.AutoText)
            self.start_date_label.setStyleSheet(f"color: {text_secondary};")
            self.automation_date_label.setText("")
            self.automation_date_label.setTextFormat(Qt.TextFormat.AutoText)
            self.automation_date_label.setStyleSheet(f"color: {text_secondary};")
            self.end_date_label.setText("")

        self.end_date_label.setStyleSheet(f"color: {text_secondary};")
    
    def start_collection(self):
        """Start document collection process."""
        if self.worker and self.worker.isRunning():
            return
        
        # Validate date selection (supports single date or date range)
        if not self.start_date:
            self._show_warning_message(
                "Date Not Selected",
                "Please select at least a start date.\n\n"
                "For a single date: Enter or click a date in the 'Start Date' field.\n"
                "For a date range: Enter or click dates in both 'Start Date' and 'End Date' fields."
            )
            return
        
        yesterday = datetime.now().date() - timedelta(days=1)
        
        # Validate: start date must not be more than yesterday
        if self.start_date > yesterday:
            self._show_warning_message(
                "Invalid Date Selection",
                "The selected date must not be more than yesterday's date.\n\n"
                "The FCC website updates 24 hours late, so today's and future dates are not available.\n\n"
                f"Selected date: {self.start_date.strftime('%Y-%m-%d')}"
            )
            self.reset_date_selection()
            return
        
        # If end_date is set, validate the range
        if self.end_date:
            # Validate: start date <= end date
            if self.start_date > self.end_date:
                self._show_warning_message(
                    "Invalid Date Range",
                    "Start date must be before or equal to end date.\n\n"
                    f"Selected: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}\n"
                    "Please adjust your date selection."
                )
                self.reset_date_selection()
                return
            
            # Validate: end date must not be more than yesterday
            if self.end_date > yesterday:
                self._show_warning_message(
                    "Invalid Date Selection",
                    "The end date must not be more than yesterday's date.\n\n"
                    "The FCC website updates 24 hours late, so today's and future dates are not available.\n\n"
                    f"Selected range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
                )
                self.reset_date_selection()
                return
        
        # Get date range (supports single date or date range)
        date_range = self.get_selected_date_range()
        if not date_range:
            self._show_warning_message(
                "Error",
                "Could not generate date list. Please try again."
            )
            return
        
        # Log message based on single date vs range
        if len(date_range) == 1:
            self.logger.info(f"Starting collection for single date: {self.start_date.strftime('%Y-%m-%d')}")
        else:
            self.logger.info(f"Starting collection for date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')} ({len(date_range)} days)")
        
        # Hide Collect button and show STOP button
        self.collect_button.setVisible(False)
        self.stop_button.setVisible(True)
        self._transition_to_running_state()
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Processing {len(date_range)} day(s)...")
        
        # Create and start worker with date range
        self.worker = CollectionWorker(date_range, self.output_dir, self.logger)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.status_updated.connect(self.update_status)
        self.worker.finished.connect(self.collection_finished)
        self.worker.start()
    
    def stop_collection(self):
        """Stop the collection process gracefully."""
        if self.worker and self.worker.isRunning():
            self.logger.info("User requested to stop collection")
            self.status_label.setText("Stopping collection...")
            # Request interruption (graceful stop)
            self.worker.requestInterruption()
            # Wait a bit for graceful shutdown, then force if needed
            if not self.worker.wait(3000):  # Wait up to 3 seconds
                # If still running after 3 seconds, terminate forcefully
                self.logger.warning("Worker did not stop gracefully, terminating...")
                self.worker.terminate()
                self.worker.wait()
                # Disconnect signals to prevent any delayed signals from causing issues
                try:
                    self.worker.finished.disconnect()
                    self.worker.progress_updated.disconnect()
                    self.worker.status_updated.disconnect()
                except:
                    pass
            
            # Reset UI immediately (don't wait for finished signal if forcefully terminated)
            self._reset_ui_after_stop()
            self.status_label.setText("Collection stopped.")
            
            # Use QTimer to reset status to "Ready." after a short delay
            # This ensures the "Collection stopped." message is visible briefly
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.status_label.setText("Ready."))
    
    def update_progress(self, current: int, total: int):
        """Update progress bar."""
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
    
    def update_status(self, message: str):
        """Update status label."""
        self.status_label.setText(message)

    def _sync_theme_wallpaper_geometry(self):
        """Keep the wallpaper layer fitted to the content widget."""
        if not hasattr(self, "theme_wallpaper_label"):
            return

        central_widget = self.centralWidget()
        if central_widget is None:
            return

        self.theme_wallpaper_label.setGeometry(central_widget.rect())
        self.theme_wallpaper_label.lower()

    def _rescale_active_wallpaper(self):
        """Rescale the currently active wallpaper to the content area."""
        if not hasattr(self, "theme_wallpaper_label") or self._active_wallpaper_source.isNull():
            return

        central_widget = self.centralWidget()
        if central_widget is None:
            return

        target_size = central_widget.size()
        if not target_size.isValid() or target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled_pixmap = self._active_wallpaper_source.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.theme_wallpaper_label.setPixmap(scaled_pixmap)

    def _hide_theme_wallpaper(self):
        """Hide the wallpaper layer."""
        if hasattr(self, "theme_wallpaper_label"):
            self.theme_wallpaper_label.clear()
            self.theme_wallpaper_label.hide()

        self._active_wallpaper_theme = None
        self._active_wallpaper_source = QPixmap()

    def _show_theme_wallpaper(self, theme_name: str):
        """Show the wallpaper for a specific theme, if one exists."""
        wallpaper_path = self.theme_backgrounds.get(theme_name)
        if not wallpaper_path or not wallpaper_path.exists():
            self._hide_theme_wallpaper()
            return

        if self._active_wallpaper_theme != theme_name or self._active_wallpaper_source.isNull():
            source_pixmap = QPixmap(str(wallpaper_path))
            if source_pixmap.isNull():
                self._hide_theme_wallpaper()
                if self.logger:
                    self.logger.warning(f"Could not load theme wallpaper: {wallpaper_path}")
                return

            self._active_wallpaper_theme = theme_name
            self._active_wallpaper_source = source_pixmap

        self._sync_theme_wallpaper_geometry()
        self._rescale_active_wallpaper()
        self.theme_wallpaper_label.show()
        self.theme_wallpaper_label.lower()

    def _update_theme_background_art(self, theme_name: str, force_wallpaper: bool = False):
        """Switch wallpaper visibility based on the active theme and blur state."""
        if theme_name in {"Kawaii", "Coffee"}:
            self._show_theme_wallpaper(theme_name)
            return

        if theme_name == "Cyberpunk" and force_wallpaper:
            self._show_theme_wallpaper(theme_name)
            return

        self._hide_theme_wallpaper()

    def _update_field_label_styles(self):
        """Apply theme-specific styling to small form labels."""
        theme = self.themes.get(self.current_theme, {})
        field_label_text = theme.get("field_label_text", theme.get("text", "#ffffff"))
        weight = theme.get("field_label_weight", "normal")

        labels = [
            getattr(self, "theme_label", None),
            getattr(self, "calendar_label", None),
            getattr(self, "start_label", None),
            getattr(self, "end_label", None),
        ]

        for label in labels:
            if label is not None:
                label.setStyleSheet(
                    f"color: {field_label_text}; font-weight: {weight}; background: transparent;"
                )

    def _update_coffee_text_effects(self):
        """Apply stronger title/label contrast for the Coffee wallpaper."""
        label_widgets = [
            getattr(self, "theme_label", None),
            getattr(self, "calendar_label", None),
            getattr(self, "start_label", None),
            getattr(self, "end_label", None),
        ]

        if self.current_theme == "Coffee":
            label_shadow = QColor(74, 44, 24, 150)
            title_shadow = QColor(56, 30, 15, 180)

            for label in label_widgets:
                if hasattr(label, "set_shadow"):
                    label.set_shadow(
                        True,
                        color=label_shadow,
                        offset=QPoint(0, 1),
                        spread=1,
                    )

            if hasattr(self, "title_bar") and getattr(self.title_bar, "title_label", None) is not None:
                self.title_bar.title_label.set_shadow(
                    True,
                    color=title_shadow,
                    offset=QPoint(0, 2),
                    spread=1,
                )
        else:
            for label in label_widgets:
                if hasattr(label, "set_shadow"):
                    label.set_shadow(False)

            if hasattr(self, "title_bar") and getattr(self.title_bar, "title_label", None) is not None:
                self.title_bar.title_label.set_shadow(False)

    def resizeEvent(self, event):
        """Keep the theme wallpaper aligned when the window layout changes."""
        super().resizeEvent(event)
        self._sync_theme_wallpaper_geometry()
        self._rescale_active_wallpaper()

    def _center_window_on_main_window(self, window: QWidget):
        """Center a child window over the main window."""
        if window is None:
            return

        parent_geometry = self.frameGeometry()
        window_size = window.frameGeometry().size()

        if not window_size.isValid() or window_size.width() <= 0 or window_size.height() <= 0:
            window_size = window.sizeHint()

        target_x = parent_geometry.x() + (parent_geometry.width() - window_size.width()) // 2
        target_y = parent_geometry.y() + (parent_geometry.height() - window_size.height()) // 2
        window.move(max(target_x, 0), max(target_y, 0))

    def _exec_centered_message_box(self, message_box: QMessageBox):
        """Show a message box centered over the main window."""
        theme = self.themes.get(self.current_theme, self.themes.get("Default", {}))
        wallpaper_path = self.theme_backgrounds.get(self.current_theme)
        wallpaper_uri = None

        if wallpaper_path and wallpaper_path.exists():
            wallpaper_uri = wallpaper_path.as_posix()

        message_box.setStyleSheet(
            ThemeManager.get_message_box_stylesheet(theme, wallpaper_uri)
        )
        message_box.ensurePolished()
        icon_label = message_box.findChild(QLabel, "qt_msgboxex_icon_label")
        if icon_label is not None:
            icon_label.hide()
        for label_name in ("qt_msgbox_label", "qt_msgbox_informativelabel"):
            label = message_box.findChild(QLabel, label_name)
            if label is not None:
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
        message_box.adjustSize()
        self._center_window_on_main_window(message_box)
        QTimer.singleShot(0, lambda: self._center_window_on_main_window(message_box))
        return message_box.exec()

    def _show_warning_message(self, title: str, message: str):
        """Show a centered warning message box."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.NoIcon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        self._exec_centered_message_box(msg_box)

    def _format_prompt_received_date(self, received_date: str) -> str:
        """Format an IRT received date value for the completion prompt."""
        received_date = (received_date or "").strip()
        if not received_date:
            return "N/A"

        date_formats = (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%m-%d-%Y %I:%M:%S %p",
            "%m-%d-%Y %I:%M %p",
            "%m-%d-%Y %H:%M:%S",
            "%m-%d-%Y %H:%M",
            "%m-%d-%Y",
        )

        for date_format in date_formats:
            try:
                return datetime.strptime(received_date, date_format).strftime("%m/%d/%Y")
            except ValueError:
                continue

        if " " in received_date:
            date_only = received_date.split(" ", 1)[0]
            for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
                try:
                    return datetime.strptime(date_only, date_format).strftime("%m/%d/%Y")
                except ValueError:
                    continue

        return received_date
    
    def collection_finished(self, success: bool, message: str, run_folder_path: str = ""):
        """Handle collection completion."""
        # Reset UI buttons
        self._reset_ui_after_stop()
        
        # Reset progress bar immediately to show process is complete
        self.progress_bar.setValue(0)
        
        if success:
            worker = getattr(self, "worker", None)
            total_downloaded = getattr(worker, "total_downloaded_count", None)
            latest_irt_record = getattr(worker, "latest_irt_record", None)

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.NoIcon)

            if total_downloaded == 0:
                self.status_label.setText("No new documents collected.")
                msg_box.setWindowTitle("No New Documents Collected")
                msg_box.setText(
                    "<p align='center'>No new documents were collected during this run.</p>"
                )
                msg_box.setTextFormat(Qt.TextFormat.RichText)

                informative_parts = [f"<p align='center'>{html.escape(message)}</p>"]
                if latest_irt_record:
                    formatted_received_date = self._format_prompt_received_date(
                        latest_irt_record.get("Received Date", "")
                    )
                    informative_parts.append(
                        (
                            "<p align='center'>"
                            "<b>Most Recent FCC Document:</b><br>"
                            f"{html.escape(latest_irt_record.get('File Name', 'N/A'))}<br>"
                            f"{html.escape(latest_irt_record.get('LNI', 'N/A'))}<br>"
                            f"{html.escape(formatted_received_date)}"
                            "</p>"
                        )
                    )

                msg_box.setInformativeText("".join(informative_parts))
            else:
                self.status_label.setText("Collection complete!")
                msg_box.setWindowTitle("Collection Complete!")
                msg_box.setText(message)

            self._exec_centered_message_box(msg_box)
            # Open run folder after user clicks OK
            if run_folder_path and os.path.exists(run_folder_path):
                self.open_folder(run_folder_path)
        else:
            # Check if it was stopped by user
            if "stopped by user" in message.lower():
                self.status_label.setText("Collection stopped.")
                # Use QTimer to reset status to "Ready." after a short delay
                # This ensures the "Collection stopped." message is visible briefly
                QTimer.singleShot(2000, lambda: self.status_label.setText("Ready."))
            else:
                normalized_message = " ".join(message.split()).lower()
                is_irt_server_error = (
                    "there is some error in the application" in normalized_message
                    and "please raise a webstar" in normalized_message
                )

                if is_irt_server_error:
                    self.status_label.setText("Unexpected Error")
                    self._show_warning_message("Unexpected Error", message)
                else:
                    self.status_label.setText(f"Error: {message}")
                    self._show_warning_message("Collection Error", message)
                # Reset to Ready after error too
                QTimer.singleShot(2000, lambda: self.status_label.setText("Ready."))
        
        # Reset date selection
        self.reset_date_selection()
    
    def _reset_ui_after_stop(self):
        """Reset UI after collection stops (either completed or stopped)."""
        # Show Collect button and hide STOP button
        self.collect_button.setVisible(True)
        self.collect_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self._transition_to_idle_state()
    
    def open_folder(self, folder_path: str):
        """Open folder in system file manager."""
        try:
            folder_path = Path(folder_path)
            if not folder_path.exists():
                self.logger.warning(f"Folder does not exist: {folder_path}")
                return
            
            system = platform.system()
            if system == "Windows":
                os.startfile(str(folder_path))
            elif system == "Darwin":  # macOS
                os.system(f'open "{folder_path}"')
            else:  # Linux and others
                os.system(f'xdg-open "{folder_path}"')
        except Exception as e:
            self.logger.error(f"Error opening folder: {e}")
            self._show_warning_message("Error", f"Could not open folder: {e}")
    
    def open_collections_folder(self):
        """Open the FCC000 Collections folder."""
        if self.output_dir and self.output_dir.exists():
            self.open_folder(str(self.output_dir))
        else:
            self._show_warning_message("Error", "Collections folder not found.")
    
    def change_theme(self, theme_name: str):
        """Change the application theme."""
        if theme_name in self.themes:
            self.current_theme = theme_name
            self.apply_theme(theme_name)
    
    def apply_theme(self, theme_name: str):
        """Apply a theme to the application."""
        if theme_name not in self.themes:
            return
        
        theme = self.themes[theme_name]
        
        # Apply stylesheet to the main window and all widgets
        stylesheet = ThemeManager.get_theme_stylesheet(theme)
        self.setStyleSheet(stylesheet)
        
        # Update title bar title color and font
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "title_label") and self.title_bar.title_label is not None:
            title_label_color = theme.get("title_color", theme["title_bar_button_color"])
            self.title_bar.title_label.setStyleSheet(
                f"color: {title_label_color}; font-weight: bold; background: transparent;"
            )
            self._apply_theme_font(self.title_bar.title_label, theme_name)
        
        # Update status label color
        self.status_label.setStyleSheet(f"color: {theme['text_secondary']};")
        self._update_field_label_styles()
        self._update_coffee_text_effects()
        
        # Update date input styles
        self._update_date_input_styles()
        self._update_date_display_labels()
        
        # Refresh calendar highlights if date range is selected
        if self.start_date or self.end_date:
            self._highlight_date_range()
        
        # Update progress bar sheen color and theme colors for dynamic text
        if hasattr(self.progress_bar, 'set_sheen_color'):
            self.progress_bar.set_sheen_color(theme['sheen_color'])
        if hasattr(self.progress_bar, 'set_theme_colors'):
            self.progress_bar.set_theme_colors(
                theme_name,
                theme.get('progress_bg', '#3d3d3d'),
                theme.get('progress_chunk', '#66BB6A'),
                theme.get('text', '#ffffff')
            )

        if theme_name == "Cyberpunk":
            self._update_theme_background_art(theme_name, force_wallpaper=False)
        else:
            self._update_theme_background_art(theme_name)
        
        # Apply acrylic blur effect for Cyberpunk theme (Windows only)
        # Use QTimer to ensure window is ready before applying blur
        if theme_name == "Cyberpunk":
            QTimer.singleShot(100, lambda: self._apply_blur_effect(theme_name))
        else:
            # For other themes, disable blur immediately
            self._apply_blur_effect(theme_name)
        
        # Ensure calendar weekday header (Sun, Mon, ...) follows theme colors.
        # Also suppress the native selected-cell highlight. We keep calendar
        # selection enabled for clickability, but the selected/range visuals are
        # drawn manually with QTextCharFormat in _highlight_date_range().
        if hasattr(self, "calendar") and self.calendar is not None:
            try:
                calendar_view = self.calendar.findChild(QTableView)
                if calendar_view is not None:
                    # Disable QTableView's grid and item borders. AdjacentMonthCalendar.paintCell()
                    # draws one clean 1px border for every date cell, preventing thick/uneven lines.
                    calendar_view.setShowGrid(False)
                    calendar_view.setStyleSheet(f"""
                        QTableView {{
                            background-color: {theme['window_bg']};
                            selection-background-color: transparent;
                            selection-color: {theme['text']};
                            outline: none;
                            border: none;
                        }}
                        QTableView::item {{
                            border: none;
                            padding: 0px;
                        }}
                        QTableView::item:selected {{
                            background: transparent;
                            color: {theme['text']};
                            border: none;
                        }}
                    """)

                    if calendar_view.horizontalHeader() is not None:
                        calendar_view.horizontalHeader().setStyleSheet(f"""
                            QHeaderView::section {{
                                background-color: {theme['secondary']};
                                color: {theme['button_text']};
                                padding: 4px;
                                border: 1px solid {theme['progress_border']};
                            }}
                        """)
                
                # Hide the downward arrow icon on the month/year button while keeping it clickable
                self.calendar.setStyleSheet(f"""
                    QCalendarWidget QToolButton::menu-indicator {{
                        image: none;
                    }}
                    QMenu::item:hover {{
                        background-color: {theme['primary']};
                        color: {theme['button_text']};
                    }}
                """)

                # Update calendar navigation arrows to match the current theme.
                self.calendar._update_calendar_nav_arrows(theme)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not style calendar weekday header: {e}")
        
        # Style adjacent month dates with muted color
        self._style_calendar_adjacent_dates()
    
    def _apply_blur_effect(self, theme_name: str):
        """Apply acrylic blur effect for Cyberpunk theme (Windows only)."""
        if theme_name != self.current_theme:
            return

        if theme_name != "Cyberpunk":
            if self._blur_enabled:
                self._blur_enabled = False
            self._update_theme_background_art(theme_name)
            return

        if not BLUR_AVAILABLE or not enable_blur:
            self._blur_enabled = False
            self._update_theme_background_art(theme_name, force_wallpaper=True)
            if self.logger:
                self.logger.info(
                    "Acrylic blur is unavailable; using Cyberpunk wallpaper fallback"
                )
            return
        
        try:
            # Wait for window to be fully shown before applying blur
            if not self.isVisible():
                QTimer.singleShot(200, lambda: self._apply_blur_effect(theme_name))
                return
            
            # Get window handle (HWND)
            hwnd = int(self.winId())
            if hwnd == 0:
                QTimer.singleShot(200, lambda: self._apply_blur_effect(theme_name))
                return
            
            # Enable acrylic blur with dark tint for Cyberpunk theme
            # Lower opacity (0x60 = ~38%) allows more blur to show through
            # Tint color: very dark (almost black) with slight cyan hint
            success = enable_blur(
                hwnd,
                acrylic=True,
                opacity=0x60,  # Lower opacity (~38%) to show more blur
                tint_color=(10, 10, 15)  # Very dark with slight blue hint
            )
            if success:
                self._blur_enabled = True
                self._update_theme_background_art(theme_name, force_wallpaper=False)
                if self.logger:
                    self.logger.info("Acrylic blur enabled for Cyberpunk theme")
            else:
                self._blur_enabled = False
                self._update_theme_background_art(theme_name, force_wallpaper=True)
                if self.logger:
                    self.logger.warning(
                        "Failed to enable acrylic blur; using Cyberpunk wallpaper fallback"
                    )
        except Exception as e:
            self._blur_enabled = False
            self._update_theme_background_art(theme_name, force_wallpaper=True)
            if self.logger:
                self.logger.warning(
                    f"Could not apply blur effect; using Cyberpunk wallpaper fallback: {e}"
                )
    
    def _apply_theme_font(self, label, theme_name):
        """Apply theme-specific font to a label."""
        font_path = self.theme_fonts.get(theme_name)
        if font_path and font_path.exists():
            try:
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        # Adjust font size per theme for better visual balance
                        if theme_name == "Cyberpunk":
                            size = 13  # Smaller; Sterion renders visually large
                        elif theme_name == "Default":
                            size = 13  # Slightly larger default header than base
                        elif theme_name == "Coffee":
                            size = 33  # Reduced to prevent overflow
                        elif theme_name == "Kawaii":
                            size = 18
                        else:
                            size = 16
                        label.setFont(QFont(families[0], size, QFont.Weight.Bold))
            except Exception as e:
                # Fallback silently to default font if custom font fails
                if self.logger:
                    self.logger.warning(f"Could not load font for theme '{theme_name}' from '{font_path}': {e}")
    
    def _is_interactive_widget(self, widget) -> bool:
        """Check if a widget is interactive (should not trigger window dragging)."""
        from PyQt6.QtWidgets import QPushButton, QCalendarWidget, QComboBox, QAbstractItemView
        return isinstance(widget, (QPushButton, QCalendarWidget, QComboBox, QAbstractItemView))
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging from anywhere."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on an interactive widget
            widget = self.childAt(event.position().toPoint())
            if widget and self._is_interactive_widget(widget):
                # Let the widget handle the event
                return super().mousePressEvent(event)
            
            # Allow dragging from non-interactive areas
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Reset drag position on mouse release."""
        self.drag_position = QPoint()
        super().mouseReleaseEvent(event)


def create_app():
    """
    Create and configure application.
    
    Returns:
        Tuple of (QApplication, MainWindow)
    """
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application icon for taskbar (works in both dev and bundled exe)
    assets_dir = get_resource_path("assets")
    icon_path = assets_dir / "fcc_bg.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = FCC000CollectorApp()
    return app, window


def main():
    """Main entry point."""
    app, window = create_app()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
