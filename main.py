"""Main entry point for FCC000 Collector application."""

import sys
from gui.main_window import create_app


def main():
    """Main entry point."""
    app, window = create_app()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

