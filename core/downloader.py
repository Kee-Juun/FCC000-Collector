"""PDF downloading and file operations."""

import logging
import time
import requests
from pathlib import Path
from typing import Optional, Dict

from utils.config import DOWNLOAD_TIMEOUT, CHUNK_SIZE, FILENAME_TEMPLATE


class PDFDownloader:
    """Handles PDF downloading and file operations."""

    MAX_DOWNLOAD_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 5

    def __init__(self, downloads_dir: Path, logger: logging.Logger):
        self.downloads_dir = downloads_dir
        self.logger = logger
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def generate_filename(self, original_filename: str) -> str:
        """
        Generate standardized filename and ensure it always ends with .pdf
        """
        # Safely remove extension
        base_name = Path(original_filename).stem

        # Apply your naming template
        new_filename = FILENAME_TEMPLATE.format(original_name=base_name)

        # Ensure .pdf extension exists
        if not new_filename.lower().endswith(".pdf"):
            new_filename += ".pdf"

        return new_filename

    def download(self, pdf_info: Dict) -> Optional[Path]:
        url = pdf_info["url"]
        original_filename = pdf_info["filename"]

        new_filename = self.generate_filename(original_filename)

        # Extra safety (never trust upstream)
        if not new_filename.lower().endswith(".pdf"):
            new_filename += ".pdf"

        filepath = self.downloads_dir / new_filename
        temp_filepath = filepath.with_suffix(filepath.suffix + ".part")

        for attempt in range(1, self.MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                if attempt == 1:
                    self.logger.info(f"Downloading: {url}")
                else:
                    self.logger.info(
                        f"Retrying download {attempt}/{self.MAX_DOWNLOAD_ATTEMPTS}: {original_filename}"
                    )

                with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
                    response.raise_for_status()

                    with open(temp_filepath, "wb") as f:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)

                temp_filepath.replace(filepath)

                # Validate file
                if filepath.exists() and filepath.stat().st_size > 0:
                    self.logger.info(f"Downloaded: {new_filename}")
                    return filepath

                raise IOError(f"Downloaded file is empty: {filepath}")

            except (
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ) as e:
                self.logger.warning(
                    f"Temporary download error for {original_filename} "
                    f"(attempt {attempt}/{self.MAX_DOWNLOAD_ATTEMPTS}): {e}"
                )

                if temp_filepath.exists():
                    try:
                        temp_filepath.unlink()
                    except Exception:
                        pass

                if attempt < self.MAX_DOWNLOAD_ATTEMPTS:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue

                self.logger.error(
                    f"Download failed after {self.MAX_DOWNLOAD_ATTEMPTS} attempts: {original_filename}"
                )
                return None

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error downloading {original_filename}: {e}")
                if temp_filepath.exists():
                    try:
                        temp_filepath.unlink()
                    except Exception:
                        pass
                return None

            except Exception as e:
                self.logger.error(f"Unexpected error downloading {original_filename}: {e}")
                if temp_filepath.exists():
                    try:
                        temp_filepath.unlink()
                    except Exception:
                        pass
                return None

        return None