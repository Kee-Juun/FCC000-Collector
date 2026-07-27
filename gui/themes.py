"""Theme definitions for GUI customization."""

from typing import Dict


class ThemeManager:
    """Manages GUI themes and styles."""
    
    @staticmethod
    def get_themes() -> Dict[str, Dict]:
        """Get all available themes."""
        return {
            "Default": ThemeManager._get_default_theme(),
            "Cyberpunk": ThemeManager._get_cyberpunk_theme(),
            "Kawaii": ThemeManager._get_kawaii_theme(),
            "Coffee": ThemeManager._get_coffee_theme()
        }
    
    @staticmethod
    def _get_default_theme() -> Dict:
        """Default theme - dark theme (original design)."""
        return {
            "name": "Default",
            "window_bg": "#2b2b2b",
            "transparent_surfaces": False,
            "field_label_text": "#ffffff",
            "field_label_weight": "normal",
            "primary": "#4CAF50",
            "primary_hover": "#45a049",
            "secondary": "#2196F3",
            "secondary_hover": "#1976D2",
            "text": "#ffffff",
            "text_secondary": "#cccccc",
            "progress_bg": "#3d3d3d",
            "progress_chunk": "#66BB6A",  # Lighter green than primary
            "progress_border": "#555555",
            "sheen_color": (255, 255, 255, 100),
            "button_text": "white",
            "title_color": "#ffffff",
            "title_bar_button_color": "#ffffff",  # White for default theme
            "stop_button": "#f44336",  # Red
            "stop_button_hover": "#da190b",  # Darker red
            "stop_button_pressed": "#b71c1c"  # Darkest red
        }
    
    @staticmethod
    def _get_cyberpunk_theme() -> Dict:
        """Cyberpunk theme - neon colors, dark background."""
        return {
            "name": "Cyberpunk",
            "window_bg": "#0a0a0a",
            "transparent_surfaces": True,
            "field_label_text": "#00ffff",
            "field_label_weight": "normal",
            "primary": "#00ffff",
            "primary_hover": "#00cccc",
            "secondary": "#ff00ff",
            "secondary_hover": "#cc00cc",
            "text": "#00ffff",
            "text_secondary": "#00cccc",
            "progress_bg": "#1a1a1a",
            "progress_chunk": "#00bcd4",  # Lighter cyan/teal than button
            "progress_border": "#00ffff",
            "sheen_color": (255, 0, 255, 180),  # Magenta sheen for contrast with cyan fill
            "button_text": "#0a0a0a",
            "title_color": "#00ffff",
            "title_bar_button_color": "#00ffff",  # Cyan for Cyberpunk
            "stop_button": "#ff0080",  # Bright magenta/pink
            "stop_button_hover": "#cc0066",  # Darker magenta
            "stop_button_pressed": "#99004d"  # Darkest magenta
        }
    
    @staticmethod
    def _get_kawaii_theme() -> Dict:
        """Kawaii theme - cutesy anime pastels."""
        return {
            "name": "Kawaii",
            "window_bg": "#fff0f5",
            "transparent_surfaces": True,
            "field_label_text": "#8b008b",
            "field_label_weight": "normal",
            "primary": "#ff69b4",
            "primary_hover": "#ff1493",
            "secondary": "#da70d6",
            "secondary_hover": "#ba55d3",
            "text": "#8b008b",
            "text_secondary": "#9370db",
            "progress_bg": "#ffe4e1",
            "progress_chunk": "#ff85c1",  # Lighter pastel pink
            "progress_border": "#ffb6c1",
            "sheen_color": (255, 182, 193, 120),
            "button_text": "white",
            "title_color": "#ff69b4",
            "title_bar_button_color": "#ff69b4",  # Pink for Kawaii
            "stop_button": "#ff6b9d",  # Soft pink-red
            "stop_button_hover": "#ff4d7a",  # Darker pink-red
            "stop_button_pressed": "#ff3366"  # Darkest pink-red
        }
    
    @staticmethod
    def _get_coffee_theme() -> Dict:
        """Coffee theme - warm browns and creams."""
        return {
            "name": "Coffee",
            "window_bg": "#f5e6d3",
            "transparent_surfaces": True,
            "field_label_text": "#ffffff",
            "field_label_weight": "bold",
            "primary": "#6f4e37",
            "primary_hover": "#5a3e2a",
            "secondary": "#8b6914",
            "secondary_hover": "#6b5010",
            "text": "#3e2723",
            "text_secondary": "#5d4037",
            "progress_bg": "#d7ccc8",
            "progress_chunk": "#8d5a3b",  # Lighter, creamier brown
            "progress_border": "#8d6e63",
            "sheen_color": (255, 248, 220, 120),
            "button_text": "#f5e6d3",
            "title_color": "#ffffff",
            "title_bar_button_color": "#6f4e37",  # Brown for Coffee
            "stop_button": "#8b4513",  # Saddle brown
            "stop_button_hover": "#6b3410",  # Darker brown
            "stop_button_pressed": "#5a2e0d"  # Darkest brown
        }
    
    @staticmethod
    def get_theme_stylesheet(theme: Dict) -> str:
        """Generate complete stylesheet for a theme."""
        use_transparent_surfaces = theme.get("transparent_surfaces", False)
        title_bar_bg = "transparent" if use_transparent_surfaces else theme["secondary"]

        # For Cyberpunk theme, use transparent/semi-transparent backgrounds to allow blur
        if theme["name"] == "Cyberpunk":
            window_bg = "transparent"  # Fully transparent to show blur
            widget_bg = "transparent"
        elif use_transparent_surfaces:
            window_bg = theme["window_bg"]
            widget_bg = "transparent"
        else:
            window_bg = theme["window_bg"]
            widget_bg = theme["window_bg"]
        
        return f"""
            QMainWindow {{
                background: {window_bg};
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            QWidget {{
                background: {widget_bg};
                color: {theme["text"]};
            }}
            QWidget#contentWidget {{
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            QLabel#themeWallpaperLabel {{
                background: transparent;
                border: none;
            }}
            QLabel {{
                background: transparent;
                color: {theme["text"]};
            }}
            QPushButton {{
                background-color: {theme["primary"]};
                color: {theme["button_text"]};
                padding: 6px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme["primary_hover"]};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
            QPushButton#viewFolderButton {{
                background-color: {theme["secondary"]};
            }}
            QPushButton#viewFolderButton:hover {{
                background-color: {theme["secondary_hover"]};
            }}
            QPushButton#stopButton {{
                background-color: {theme["stop_button"]};
                color: {theme["button_text"]};
                border: none;
                padding: 6px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton#stopButton:hover {{
                background-color: {theme["stop_button_hover"]};
            }}
            QPushButton#stopButton:pressed {{
                background-color: {theme["stop_button_pressed"]};
            }}
            QProgressBar {{
                border: 2px solid {theme["progress_border"]};
                border-radius: 4px;
                text-align: center;
                height: 20px;
                background-color: {theme["progress_bg"]};
                color: {theme["text"]};
            }}
            QProgressBar::chunk {{
                background-color: {theme["progress_chunk"]};
                border-radius: 2px;
            }}
            QCalendarWidget {{
                background-color: {theme["window_bg"]};
                color: {theme["text"]};
                border: 1px solid {theme["progress_border"]};
                border-radius: 4px;
            }}
            QCalendarWidget QTableView {{
                selection-background-color: {theme["primary"]};
                selection-color: {theme["button_text"]};
                border-left: 1px solid {theme["progress_border"]};
                border-right: 1px solid {theme["progress_border"]};
                gridline-color: {theme["progress_border"]};
            }}
            /* Day-of-week header row (Sun, Mon, ...) */
            QCalendarWidget QTableView::horizontalHeader {{
                background-color: {theme["secondary"]};
            }}
            QCalendarWidget QTableView::horizontalHeader::section {{
                background-color: {theme["secondary"]};
                color: {theme["button_text"]};
                padding: 4px;
                border: 1px solid {theme["progress_border"]};
            }}
            QCalendarWidget QToolButton {{
                background-color: {theme["primary"]};
                color: {theme["button_text"]};
                border: 1px solid {theme["primary_hover"]};
                border-radius: 4px;
                padding: 2px 6px;
                font-weight: bold;
            }}
            QCalendarWidget QToolButton:hover {{
                background-color: {theme["secondary"]};
                color: {theme["button_text"]};
                border: 1px solid {theme["secondary_hover"]};
            }}
            QCalendarWidget QToolButton:pressed {{
                background-color: {theme["secondary_hover"]};
                color: {theme["button_text"]};
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QCalendarWidget QMenu {{
                background-color: {theme["window_bg"]};
                color: {theme["text"]};
                border: 1px solid {theme["progress_border"]};
            }}
            QCalendarWidget QMenu::item {{
                padding: 4px 12px;
            }}
            QCalendarWidget QMenu::item:selected, QCalendarWidget QMenu::item:hover {{
                background-color: {theme["primary"]};
                color: {theme["button_text"]};
            }}
            QComboBox {{
                background-color: {theme["window_bg"]};
                color: {theme["text"]};
                border: 1px solid {theme["progress_border"]};
                border-radius: 4px;
                padding: 4px;
            }}
            QComboBox:hover {{
                border: 1px solid {theme["primary"]};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme["window_bg"]};
                color: {theme["text"]};
                selection-background-color: {theme["primary"]};
                selection-color: {theme["button_text"]};
            }}
            QWidget#customTitleBar {{
                background-color: {title_bar_bg};
                border-bottom: 1px solid {theme["progress_border"]};
            }}
            QWidget#customTitleBar QLabel {{
                color: {theme["button_text"]};
            }}
            QWidget#customTitleBar QPushButton#minimizeButton {{
                background-color: transparent;
                color: {theme["title_bar_button_color"]};
                border: none;
                border-radius: 2px;
            }}
            QWidget#customTitleBar QPushButton#minimizeButton:hover {{
                background-color: {theme["secondary_hover"]};
            }}
            QWidget#customTitleBar QPushButton#closeButton {{
                background-color: transparent;
                color: {theme["title_bar_button_color"]};
                border: none;
                border-radius: 2px;
            }}
            QWidget#customTitleBar QPushButton#closeButton:hover {{
                background-color: #e81123;
                color: white;
            }}
        """

    @staticmethod
    def get_message_box_stylesheet(theme: Dict, wallpaper_path: str | None = None) -> str:
        """Generate a themed stylesheet for QMessageBox dialogs."""
        theme_name = theme.get("name", "Default")

        if theme_name == "Coffee":
            dialog_text = "#4a2c18"
            label_panel_bg = "rgba(255, 249, 241, 225)"
            label_border = "#b78d67"
        elif theme_name == "Kawaii":
            dialog_text = "#8b008b"
            label_panel_bg = "rgba(255, 250, 252, 220)"
            label_border = "#f4b6d7"
        elif theme_name == "Cyberpunk":
            dialog_text = theme.get("text", "#00ffff")
            label_panel_bg = "rgba(8, 12, 20, 220)"
            label_border = "#00ffff"
        else:
            dialog_text = theme.get("text", "#ffffff")
            label_panel_bg = "rgba(43, 43, 43, 220)"
            label_border = theme.get("progress_border", "#555555")

        dialog_bg = theme.get("window_bg", "#2b2b2b")
        wallpaper_css = ""
        if wallpaper_path:
            wallpaper_css = (
                f'background-image: url("{wallpaper_path}");'
                "background-position: center;"
                "background-repeat: no-repeat;"
            )

        return f"""
            QMessageBox {{
                background-color: {dialog_bg};
                {wallpaper_css}
                color: {dialog_text};
            }}
            QMessageBox QLabel {{
                color: {dialog_text};
                background: transparent;
            }}
            QMessageBox QLabel#qt_msgbox_label,
            QMessageBox QLabel#qt_msgbox_informativelabel {{
                background-color: {label_panel_bg};
                border: 1px solid {label_border};
                border-radius: 8px;
                padding: 8px;
            }}
            QMessageBox QLabel#qt_msgboxex_icon_label {{
                background: transparent;
                border: none;
            }}
            QMessageBox QPushButton {{
                background-color: {theme.get("primary", "#4CAF50")};
                color: {theme.get("button_text", "white")};
                border: 1px solid {theme.get("primary_hover", "#45a049")};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                min-width: 72px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {theme.get("primary_hover", "#45a049")};
            }}
            QMessageBox QPushButton:pressed {{
                background-color: {theme.get("secondary_hover", theme.get("primary_hover", "#45a049"))};
            }}
        """
