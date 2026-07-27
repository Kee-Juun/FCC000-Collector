"""Custom GUI widgets."""

from PyQt6.QtWidgets import QProgressBar, QLabel
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFontMetrics


class ShadowLabel(QLabel):
    """Label that can paint a strong text shadow without using graphics effects."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._shadow_enabled = False
        self._shadow_color = QColor(0, 0, 0, 220)
        self._shadow_offset = QPoint(0, 2)
        self._shadow_spread = 2

    def set_shadow(
        self,
        enabled: bool,
        color: QColor | None = None,
        offset: QPoint | None = None,
        spread: int | None = None,
    ):
        """Configure shadow rendering for the label text."""
        self._shadow_enabled = enabled

        if color is not None:
            self._shadow_color = QColor(color)
        if offset is not None:
            self._shadow_offset = QPoint(offset)
        if spread is not None:
            self._shadow_spread = max(0, int(spread))

        self.update()

    def paintEvent(self, event):
        """Paint shadow first, then the regular label text."""
        if self._shadow_enabled and self.text():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(self.font())
            painter.setPen(self._shadow_color)

            alignment_flags = int(self.alignment())
            if self.wordWrap():
                alignment_flags |= int(Qt.TextFlag.TextWordWrap)

            base_rect = self.contentsRect().translated(self._shadow_offset)
            spread = self._shadow_spread

            for dx in range(-spread, spread + 1):
                for dy in range(-spread, spread + 1):
                    painter.drawText(
                        base_rect.translated(dx, dy),
                        alignment_flags,
                        self.text(),
                    )

            painter.end()

        super().paintEvent(event)


class AnimatedProgressBar(QProgressBar):
    """Progress bar with sheen animation effect."""
    
    def __init__(self, parent=None):
        """Initialize animated progress bar."""
        super().__init__(parent)
        self._sheen_offset = 0.0  # Continuous offset (like old implementation)
        self.sheen_color = (255, 255, 255, 100)  # Default white sheen
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_sheen)
        self.animation_timer.start(30)  # Update every 30ms for smoother animation
        
        # Theme colors for dynamic text color
        self.progress_bg_color = None
        self.progress_chunk_color = None
        self.text_color = None
        self.theme_name = "Default"
        self.use_dynamic_text_color = False  # Only for Cyberpunk, Kawaii, Coffee
    
    def set_sheen_color(self, color: tuple):
        """
        Set the sheen color.
        
        Args:
            color: Tuple of (r, g, b, alpha) values
        """
        self.sheen_color = color
        self.update()
    
    def set_theme_colors(self, theme_name: str, progress_bg: str, progress_chunk: str, text_color: str):
        """
        Set theme colors for dynamic text color adjustment.
        
        Args:
            theme_name: Name of the theme
            progress_bg: Background color (hex string)
            progress_chunk: Fill color (hex string)
            text_color: Default text color (hex string)
        """
        self.theme_name = theme_name
        self.progress_bg_color = QColor(progress_bg)
        self.progress_chunk_color = QColor(progress_chunk)
        self.text_color = QColor(text_color)
        # Only use dynamic text color for Cyberpunk, Kawaii, and Coffee
        self.use_dynamic_text_color = theme_name in ["Cyberpunk", "Kawaii", "Coffee"]
        
        # Set text visibility once (not during paintEvent to avoid recursive repaints)
        if self.use_dynamic_text_color:
            self.setTextVisible(False)  # Hide default text, we'll draw it manually
        else:
            self.setTextVisible(True)  # Show default text for Default theme
        
        self.update()
        
    def update_sheen(self):
        """Update sheen position for animation."""
        # Continuous increment (like old implementation)
        self._sheen_offset += 6.0
        # Reset at large threshold to avoid precision issues
        if self._sheen_offset > 10000:
            self._sheen_offset = 0.0
        self.update()
    
    def paintEvent(self, event):
        """Custom paint event with sheen effect and dynamic text color."""
        # Draw the base progress bar (background and fill)
        # Text visibility is already set correctly in set_theme_colors, so no need to change it here
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate the filled portion of the progress bar
        min_val = self.minimum()
        max_val = self.maximum()
        current_val = self.value()
        progress_ratio = (current_val - min_val) / (max_val - min_val) if max_val > min_val else 0
        filled_width = int(self.width() * progress_ratio)
        
        # Draw sheen if there's progress
        if self.value() > 0 and filled_width > 0:
            # KEY INSIGHT: Use TOTAL bar width for sheen calculation (like old implementation)
            # This allows the sheen to smoothly traverse across the entire bar,
            # but it's clipped to only show within the filled portion
            total_width = self.width()
            sheen_width = total_width * 0.25  # 25% of total width (like old implementation)
            
            # Calculate offset span: total width + 2x sheen width
            # This allows sheen to start before visible area and end after
            offset_span = total_width + sheen_width * 2
            
            # Calculate sheen X position: modulo on offset_span, then subtract sheen_width
            # This positions sheen relative to the filled rect
            x = (self._sheen_offset % offset_span) - sheen_width
            
            # Create sheen gradient positioned at fill_rect.left() + x
            # The gradient spans sheen_width pixels
            r, g, b, base_alpha = self.sheen_color
            sheen_gradient = QLinearGradient(x, 0, x + sheen_width, 0)
            sheen_gradient.setColorAt(0.0, QColor(r, g, b, 0))
            sheen_gradient.setColorAt(0.5, QColor(r, g, b, base_alpha))
            sheen_gradient.setColorAt(1.0, QColor(r, g, b, 0))
            
            # Clip to filled portion only - this creates the smooth effect
            # The sheen moves across the entire bar width continuously,
            # but only the portion within the filled area is visible
            painter.setClipRect(0, 0, filled_width, self.height())
            painter.fillRect(0, 0, filled_width, self.height(), sheen_gradient)
            painter.setClipping(False)  # Reset clipping
        
        # Draw text with dynamic color if enabled (always draw, even at 0%)
        if self.use_dynamic_text_color and self.text_color and self.progress_bg_color:
            text = self.text()
            if text:
                # Get text metrics to center it
                fm = QFontMetrics(self.font())
                text_width = fm.horizontalAdvance(text)
                text_height = fm.height()
                
                # Calculate text position (centered) - match Qt's default centering
                text_x = (self.width() - text_width) // 2
                # Use Qt's standard vertical centering formula
                text_y = (self.height() + fm.ascent() - fm.descent()) // 2
                
                # Determine if text center is over filled or background portion
                text_center_x = text_x + text_width // 2
                
                # Choose color based on position
                if text_center_x < filled_width:
                    # Text is over filled portion - use background color for contrast
                    painter.setPen(self.progress_bg_color)
                else:
                    # Text is over background portion - use default text color
                    painter.setPen(self.text_color)
                
                # Draw the text
                painter.setFont(self.font())
                painter.drawText(text_x, text_y, text)
        
        painter.end()

