"""Build script for creating standalone executable."""

import PyInstaller.__main__
import sys
import os
from pathlib import Path

# Get project root directory
project_root = Path(__file__).parent.resolve()
icon_path = project_root / "assets" / "fcc_bg.ico"
assets_dir = project_root / "assets"

# PyInstaller arguments
args = [
    "main.py",  # Main script
    "--name=FCC000_Collector",  # Executable name
    "--onefile",  # Create a single file executable
    "--windowed",  # No console window (GUI app)
    f"--icon={icon_path}",  # Application icon
    "--add-data", f"{assets_dir}{os.pathsep}assets",  # Include assets folder
    "--hidden-import=PyQt6.QtCore",
    "--hidden-import=PyQt6.QtGui",
    "--hidden-import=PyQt6.QtWidgets",
    "--hidden-import=selenium",
    "--hidden-import=selenium.webdriver",
    "--hidden-import=selenium.webdriver.chrome",
    "--hidden-import=selenium.webdriver.chrome.service",
    "--hidden-import=selenium.webdriver.chrome.options",
    "--hidden-import=selenium.webdriver.common.by",
    "--hidden-import=selenium.webdriver.support",
    "--hidden-import=selenium.webdriver.support.ui",
    "--hidden-import=selenium.webdriver.support.expected_conditions",
    "--hidden-import=bs4",
    "--hidden-import=openpyxl",
    "--hidden-import=requests",
    "--collect-all=selenium",
    "--noconfirm",  # Overwrite output without asking
    "--clean",  # Clean cache before building
]

if __name__ == "__main__":
    print("Building FCC000 Collector executable...")
    print(f"Icon path: {icon_path}")
    print(f"Assets directory: {assets_dir}")
    
    if not icon_path.exists():
        print(f"WARNING: Icon file not found at {icon_path}")
    
    if not assets_dir.exists():
        print(f"WARNING: Assets directory not found at {assets_dir}")
    
    try:
        PyInstaller.__main__.run(args)
        print("\nBuild complete! Executable should be in the 'dist' folder.")
    except Exception as e:
        print(f"\nBuild failed: {e}")
        sys.exit(1)

