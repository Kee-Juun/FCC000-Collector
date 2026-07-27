"""Configuration constants for FCC000 Collector."""

import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """
    Get resource path that works both in development and when bundled as executable.
    
    Args:
        relative_path: Relative path from project root
        
    Returns:
        Path to the resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Running as script, use project root
        base_path = Path(__file__).resolve().parent.parent
    
    return base_path / relative_path

# FCC Website Configuration
FCC_BASE_URL = "https://www.fcc.gov/edocs/daily-digest"
FCC_URL_TEMPLATE = f"{FCC_BASE_URL}/{{year}}/{{month}}/{{day}}"

# File Naming Templates
FILENAME_TEMPLATE = "LDC_SMD_{original_name}_E2E.pdf"
REPORT_FILENAME_TEMPLATE = "Report_FCC000_{timestamp}.xlsx"
LOG_FILENAME_TEMPLATE = "Log_FCC000_{timestamp}.txt"
TIMESTAMP_FORMAT = "%m-%d-%Y_%I-%M-%S_%p"

# Directory Configuration
OUTPUT_FOLDER_NAME = "FCC000 Collections"
DOWNLOADS_SUBFOLDER = "downloads"
DATABASE_FILENAME = "document_database.json"
LOG_FILENAME = "fcc000_collector.log"

# Browser Configuration
BROWSER_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 30
CHUNK_SIZE = 8192

# Chrome Options
CHROME_OPTIONS = [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu"
]

# Excel Report Configuration
EXCEL_SHEET_NAME = "Downloaded Documents"
EXCEL_HEADERS = ['Document Number', 'Filename']
MAX_COLUMN_WIDTH = 50

