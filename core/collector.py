"""Main collection worker that coordinates the document collection process."""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re

from PyQt6.QtCore import QThread, pyqtSignal

from core.browser import BrowserAutomation
from core.downloader import PDFDownloader
from core.duplicate_checker import OnlineDuplicateChecker, IRTServerUnavailableError
from core.webdriver_factory import ChromeStartupError
from utils.reports import ReportGenerator
from utils.config import FCC_URL_TEMPLATE, TIMESTAMP_FORMAT, FILENAME_TEMPLATE, LOG_FILENAME


class CollectionWorker(QThread):
    """Worker thread for document collection automation."""

    progress_updated = pyqtSignal(int, int)  # current, total
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)  # success, message, run_folder_path

    def __init__(self, date_list: List[str], output_dir: Path, logger: logging.Logger):
        """
        Initialize collection worker.

        Args:
            date_list: List of date strings in YYYY/MM/DD format
            output_dir: Base output directory
            logger: Logger instance
        """
        super().__init__()
        self.date_list = date_list if isinstance(date_list, list) else [date_list]
        self.base_output_dir = output_dir
        self.logger = logger

        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        run_folder_name = f"FCC000_{timestamp}"
        self.output_dir = output_dir / run_folder_name
        self.output_dir.mkdir(exist_ok=True)
        self.logger.info(f"Created run folder: {self.output_dir}")

        from utils.config import LOG_FILENAME_TEMPLATE
        log_filename = LOG_FILENAME_TEMPLATE.format(timestamp=timestamp)
        self.log_file_path = self.output_dir / log_filename

        self.run_file_handler = logging.FileHandler(self.log_file_path)
        self.run_file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.run_file_handler.setFormatter(formatter)
        self.logger.addHandler(self.run_file_handler)
        self.date_file_handler: Optional[logging.FileHandler] = None

        self.downloads_dir = self.output_dir
        self.downloads_dir.mkdir(exist_ok=True)

        self.browser = BrowserAutomation(logger, headless=True)
        self.downloader = PDFDownloader(self.downloads_dir, logger)
        self.duplicate_checker = OnlineDuplicateChecker(logger, headless=True)
        self.report_generator = ReportGenerator(self.output_dir, logger)
        self.logger.info(f"Report generator initialized with output_dir: {self.output_dir}")

        self.downloaded_files: List[Dict] = []
        self.duplicate_files: List[Dict] = []
        self.current_date_index = 0
        self.total_dates = len(self.date_list)
        self.total_items_processed = 0
        self.total_items_to_process = 0
        self.total_downloaded_count = 0
        self.total_duplicate_count = 0
        self.latest_irt_record: Optional[Dict] = None

    def _build_url(self, date_str: str) -> str:
        """Build FCC URL from date string."""
        year, month, day = date_str.split("/")
        return FCC_URL_TEMPLATE.format(year=year, month=month, day=day)

    def _generate_renamed_filename(self, original_filename: str) -> str:
        """
        Generate renamed filename according to template.

        This is for download/report naming only.
        Duplicate checking should use normalized base document IDs instead.
        """
        base_name = Path(original_filename).stem
        new_filename = FILENAME_TEMPLATE.format(original_name=base_name)

        if not new_filename.lower().endswith(".pdf"):
            new_filename += ".pdf"

        return new_filename

    def _get_date_folder_name(self, date_str: str) -> str:
        """Convert date string YYYY/MM/DD to MM-DD-YYYY."""
        year, month, day = date_str.split("/")
        return f"{month}-{day}-{year}"

    def _format_date_for_display(self, date_str: str) -> str:
        """Convert date string YYYY/MM/DD to MM/DD/YYYY."""
        year, month, day = date_str.split("/")
        return f"{month}/{day}/{year}"

    def _get_irt_duplicate_date_range(self) -> tuple[str, str]:
        """
        Build IRT duplicate-check date range in MM-DD-YYYY format.

        Duplicate-check range only:
        - Start date = one month before the user's first selected collection date
        - End date = current date

        This helps catch documents that may have already been collected on nearby/past dates.
        """
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        user_start_raw = self.date_list[0]
        user_start_dt = datetime.strptime(user_start_raw, "%Y/%m/%d")

        adjusted_start_dt = user_start_dt - relativedelta(months=1)
        current_end_dt = datetime.now()

        return adjusted_start_dt.strftime("%m-%d-%Y"), current_end_dt.strftime("%m-%d-%Y")

    def _get_recent_irt_lookup_date_range(self) -> tuple[str, str]:
        """
        Build the last-1-month IRT lookup range in MM-DD-YYYY format.

        Used only when no new FCC documents were downloaded during the run.
        """
        from dateutil.relativedelta import relativedelta

        current_end_dt = datetime.now()
        recent_start_dt = current_end_dt - relativedelta(months=1)

        return recent_start_dt.strftime("%m-%d-%Y"), current_end_dt.strftime("%m-%d-%Y")

    def _filter_attachment_pdfs(self, pdf_links: List[Dict]) -> List[Dict]:
        """
        Filter attachment PDFs so only A1 is kept for a document family.
        """
        attachment_pattern = re.compile(
            r"^(?P<base>.+?)A(?P<attachment_num>\d+)\.pdf$",
            re.IGNORECASE,
        )

        attachment_groups = {}

        for pdf_info in pdf_links:
            filename = pdf_info.get("filename", "")
            match = attachment_pattern.match(filename)
            if match:
                base_name = match.group("base").upper()
                attachment_groups.setdefault(base_name, set()).add(
                    int(match.group("attachment_num"))
                )

        if not attachment_groups:
            return pdf_links

        filtered_links: List[Dict] = []
        skipped_count = 0

        for pdf_info in pdf_links:
            filename = pdf_info.get("filename", "")
            match = attachment_pattern.match(filename)

            if not match:
                filtered_links.append(pdf_info)
                continue

            base_name = match.group("base").upper()
            attachment_num = int(match.group("attachment_num"))

            if attachment_num == 1:
                filtered_links.append(pdf_info)
            else:
                skipped_count += 1
                self.logger.info(
                    f"Skipping attachment copy for {base_name}: {filename} "
                    f"(keeping only A1 when attachments are present)"
                )

        missing_a1_bases = [base for base, nums in attachment_groups.items() if 1 not in nums]
        for base in missing_a1_bases:
            self.logger.warning(
                f"Attachment variants found for {base}, but no A1 PDF was present. "
                f"All A2/A3/etc. copies for this document were skipped."
            )

        self.logger.info(
            f"Attachment filter applied: kept {len(filtered_links)} PDFs, "
            f"skipped {skipped_count} attachment copies"
        )
        return filtered_links

    def run(self):
        """Main collection process - processes each date sequentially."""
        try:
            total_downloaded = 0
            total_duplicates = 0
            latest_irt_record: Optional[Dict] = None
            latest_irt_lookup_range: Optional[str] = None

            use_date_subfolders = len(self.date_list) > 1

            # Load IRT duplicate report once before processing FCC PDFs.
            existing_documents_by_id: Dict[str, List[Dict]] = {}
            bulk_duplicate_lookup_available = False

            try:
                irt_start_date, irt_end_date = self._get_irt_duplicate_date_range()

                self.logger.info(
                    f"Preparing bulk duplicate check using IRT received date range: "
                    f"{irt_start_date} to {irt_end_date}"
                )
                self.status_updated.emit("Loading IRT Database...")

                existing_documents_by_id = (
                    self.duplicate_checker.load_existing_documents_by_date_range(
                        start_date=irt_start_date,
                        end_date=irt_end_date,
                    )
                )

                bulk_duplicate_lookup_available = bool(
                    getattr(self.duplicate_checker, "_last_bulk_load_success", False)
                )

                if bulk_duplicate_lookup_available:
                    total_existing_records = sum(
                        len(records) for records in existing_documents_by_id.values()
                    )
                    self.logger.info(
                        f"Bulk duplicate map ready: "
                        f"{len(existing_documents_by_id)} document ID(s), "
                        f"{total_existing_records} IRT record(s)"
                    )
                    self.status_updated.emit("Duplicate report loaded from IRT")
                else:
                    self.logger.warning(
                        "Bulk duplicate map could not be loaded. "
                        "Fallback one-by-one IRT duplicate search will be used."
                    )
                    self.status_updated.emit(
                        "Duplicate report unavailable; using fallback duplicate checks"
                    )

            except ChromeStartupError:
                raise
            except IRTServerUnavailableError as e:
                reason = str(e)
                self.logger.error(f"Unexpected Error: {reason}")
                self.status_updated.emit("Unexpected Error")
                self.finished.emit(False, reason, str(self.output_dir))
                return
            except Exception as e:
                bulk_duplicate_lookup_available = False
                self.logger.warning(
                    f"Bulk duplicate setup failed; fallback duplicate checking will be used. "
                    f"{type(e).__name__}: {e!r}"
                )
                self.status_updated.emit(
                    "Duplicate report unavailable; using fallback duplicate checks"
                )

            for date_idx, date_str in enumerate(self.date_list, 1):
                if self.isInterruptionRequested():
                    self.logger.info("Collection interrupted by user")
                    self.status_updated.emit("Collection stopped by user")
                    self.finished.emit(False, "Collection stopped by user", str(self.output_dir))
                    return

                self.current_date_index = date_idx
                self.logger.info(f"Processing date {date_idx}/{self.total_dates}: {date_str}")
                self.status_updated.emit(f"Processing date {date_idx}/{self.total_dates}: {date_str}")

                if use_date_subfolders:
                    date_folder_name = self._get_date_folder_name(date_str)
                    date_output_dir = self.output_dir / date_folder_name
                    date_output_dir.mkdir(exist_ok=True)
                    self.logger.info(f"Created date folder: {date_output_dir}")

                    self.downloader = PDFDownloader(date_output_dir, self.logger)
                    date_report_generator = ReportGenerator(date_output_dir, self.logger)

                    from utils.config import LOG_FILENAME_TEMPLATE
                    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
                    date_log_filename = LOG_FILENAME_TEMPLATE.format(timestamp=timestamp)
                    date_log_path = date_output_dir / date_log_filename

                    self.date_file_handler = logging.FileHandler(date_log_path)
                    self.date_file_handler.setLevel(logging.INFO)
                    formatter = logging.Formatter(
                        "%(asctime)s - %(levelname)s - %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                    self.date_file_handler.setFormatter(formatter)
                    self.logger.addHandler(self.date_file_handler)
                else:
                    date_output_dir = self.output_dir
                    date_report_generator = self.report_generator
                    date_log_path = self.log_file_path

                url = self._build_url(date_str)
                display_date = self._format_date_for_display(date_str)

                if date_idx == 1:
                    self.status_updated.emit("Launching Chrome browser...")

                self.status_updated.emit(
                    f"[{date_idx}/{self.total_dates}] Extracting links for {display_date}..."
                )

                pdf_links = self.browser.extract_pdf_links(url)
                pdf_links = self._filter_attachment_pdfs(pdf_links)

                if not pdf_links:
                    page_title = self.browser.driver.title if self.browser.driver else ""
                    if "Page Not Found" in page_title:
                        self.logger.warning(f"Page not found for date {date_str}. Skipping...")
                        self.status_updated.emit(
                            f"[{date_idx}/{self.total_dates}] No page found for {display_date}. Skipping..."
                        )
                    else:
                        self.logger.info(f"No PDF links found for date {date_str}. Skipping...")
                        self.status_updated.emit(
                            f"[{date_idx}/{self.total_dates}] No documents found for {display_date}. Skipping..."
                        )

                    if use_date_subfolders:
                        self._close_file_handler("date_file_handler")
                    continue

                date_total = len(pdf_links)
                date_downloaded = 0
                date_duplicates = 0
                date_downloaded_files = []
                date_duplicate_files = []

                for pdf_idx, pdf_info in enumerate(pdf_links, 1):
                    if self.isInterruptionRequested():
                        self.logger.info("Collection interrupted by user")
                        self.status_updated.emit("Collection stopped by user")
                        self.finished.emit(False, "Collection stopped by user", str(self.output_dir))
                        return

                    doc_number = pdf_info["doc_number"]
                    original_filename = pdf_info["filename"]

                    self.status_updated.emit(
                        f"[{date_idx}/{self.total_dates}] {display_date} - Checking: {doc_number}..."
                    )

                    duplicate_records: List[Dict] = []

                    if bulk_duplicate_lookup_available:
                        # Correct primary behavior:
                        # Use original/base FCC filename for duplicate check.
                        # Do NOT use LDC_SMD_*_E2E.pdf here.
                        duplicate_records = self.duplicate_checker.get_duplicate_records(
                            original_filename,
                            existing_documents_by_id,
                        )
                    else:
                        # Fallback behavior:
                        # Still search using base/original document ID, not renamed download filename.
                        normalized_id = self.duplicate_checker.normalize_document_id(original_filename)
                        fallback_search_value = normalized_id or original_filename
                        is_duplicate, duplicate_records = self.duplicate_checker.check_duplicate(
                            fallback_search_value
                        )
                        if not is_duplicate:
                            duplicate_records = []

                    if duplicate_records:
                        self.logger.info(f"Duplicate found: {doc_number}")
                        self.status_updated.emit(
                            f"[{date_idx}/{self.total_dates}] {display_date} - Duplicate: {doc_number}"
                        )

                        for record in duplicate_records:
                            date_duplicate_files.append(record)
                            self.duplicate_files.append(record)

                        date_duplicates += 1
                        total_duplicates += 1
                    else:
                        self.status_updated.emit(
                            f"[{date_idx}/{self.total_dates}] {display_date} - Downloading: {doc_number}..."
                        )

                        filepath = self.downloader.download(pdf_info)

                        if filepath:
                            new_filename = filepath.name
                            file_info = {
                                "Document Number": doc_number,
                                "Filename": new_filename,
                                "Date": date_str,
                            }
                            date_downloaded_files.append(file_info)
                            self.downloaded_files.append(file_info)
                            date_downloaded += 1
                            total_downloaded += 1
                        else:
                            self.status_updated.emit(
                                f"[{date_idx}/{self.total_dates}] {display_date} - Failed: {doc_number}"
                            )

                    self.total_items_processed += 1

                    if pdf_idx == 1:
                        self.total_items_to_process += date_total

                    self.progress_updated.emit(
                        self.total_items_processed,
                        max(self.total_items_to_process, self.total_items_processed),
                    )

                if use_date_subfolders:
                    self.status_updated.emit(
                        f"[{date_idx}/{self.total_dates}] {display_date} - Creating reports..."
                    )

                    date_report_generator.create_excel_report(
                        date_downloaded_files,
                        date_duplicate_files if date_duplicate_files else None,
                    )

                    date_report_generator.create_log_report(
                        date_str,
                        date_downloaded_files,
                        date_duplicate_files,
                        date_log_path,
                    )

                    self._close_file_handler("date_file_handler")

                self.logger.info(
                    f"Date {date_str} complete: {date_downloaded} downloaded, "
                    f"{date_duplicates} duplicates"
                )
                self.status_updated.emit(
                    f"[{date_idx}/{self.total_dates}] {display_date} - Complete: "
                    f"{date_downloaded} downloaded, {date_duplicates} duplicates"
                )

            if self.isInterruptionRequested():
                self.logger.info("Collection interrupted by user before report generation")
                self.status_updated.emit("Collection stopped by user")
                self.finished.emit(False, "Collection stopped by user", str(self.output_dir))
                return

            if total_downloaded == 0:
                recent_irt_start_date, recent_irt_end_date = self._get_recent_irt_lookup_date_range()
                latest_irt_lookup_range = (
                    f"{recent_irt_start_date} to {recent_irt_end_date}"
                )

                self.logger.info(
                    "No new documents were downloaded. Looking up the most recent IRT "
                    f"record using received date range: {latest_irt_lookup_range}"
                )
                self.status_updated.emit(
                    "No new documents downloaded. Checking latest IRT record..."
                )

                latest_irt_record = self.duplicate_checker.get_most_recent_received_record(
                    start_date=recent_irt_start_date,
                    end_date=recent_irt_end_date,
                )

                if latest_irt_record:
                    self.logger.info(
                        "Latest IRT record for zero-download run: "
                        f"LNI={latest_irt_record.get('LNI', 'N/A')}, "
                        f"Received Date={latest_irt_record.get('Received Date', 'N/A')}"
                    )
                    self.status_updated.emit(
                        "Latest IRT record found for zero-download run"
                    )
                else:
                    self.logger.warning(
                        "No latest IRT record could be determined for the zero-download run."
                    )
                    self.status_updated.emit(
                        "No recent IRT record found for zero-download run"
                    )

            if use_date_subfolders:
                self.status_updated.emit("Creating overall summary report...")

                self.report_generator.create_excel_report(
                    self.downloaded_files,
                    self.duplicate_files if self.duplicate_files else None,
                    latest_irt_record=latest_irt_record,
                    latest_irt_date_range=latest_irt_lookup_range,
                )

                date_range_str = f"{self.date_list[0]} to {self.date_list[-1]}"
                self.report_generator.create_log_report(
                    date_range_str,
                    self.downloaded_files,
                    self.duplicate_files,
                    self.log_file_path,
                    latest_irt_record=latest_irt_record,
                    latest_irt_date_range=latest_irt_lookup_range,
                )
            else:
                self.status_updated.emit("Creating reports...")

                self.report_generator.create_excel_report(
                    self.downloaded_files,
                    self.duplicate_files if self.duplicate_files else None,
                    latest_irt_record=latest_irt_record,
                    latest_irt_date_range=latest_irt_lookup_range,
                )

                date_range_str = self.date_list[0]
                self.report_generator.create_log_report(
                    date_range_str,
                    self.downloaded_files,
                    self.duplicate_files,
                    self.log_file_path,
                    latest_irt_record=latest_irt_record,
                    latest_irt_date_range=latest_irt_lookup_range,
                )

            self.total_downloaded_count = total_downloaded
            self.total_duplicate_count = total_duplicates
            self.latest_irt_record = latest_irt_record

            success_msg = (
                f"Processed {self.total_dates} day(s). "
                f"Downloaded {total_downloaded} new documents, "
                f"{total_duplicates} duplicates found."
            )

            self.finished.emit(True, success_msg, str(self.output_dir))

        except ChromeStartupError as e:
            reason = str(e)
            self.logger.error(f"Collection stopped because Chrome could not start: {reason}")
            self.status_updated.emit("Chrome could not be started")
            self.finished.emit(False, reason, str(self.output_dir))
        except IRTServerUnavailableError as e:
            reason = str(e)
            self.logger.error(f"Unexpected Error: {reason}")
            self.status_updated.emit("Unexpected Error")
            self.finished.emit(False, reason, str(self.output_dir))
        except Exception as e:
            self.logger.error(f"Collection error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.finished.emit(False, f"Error: {str(e)}", str(self.output_dir))

        finally:
            try:
                if hasattr(self, "duplicate_checker"):
                    self.duplicate_checker.quit()

                if hasattr(self, "browser") and hasattr(self.browser, "driver") and self.browser.driver:
                    try:
                        self.browser.driver.quit()
                    except Exception:
                        pass

            except Exception as cleanup_error:
                self.logger.warning(f"Error during cleanup: {cleanup_error}")
            finally:
                self._close_file_handler("date_file_handler")
                self._close_file_handler("run_file_handler")

    def _close_file_handler(self, attribute_name: str):
        """Remove and close a worker-owned log handler exactly once."""
        handler = getattr(self, attribute_name, None)
        if handler is None:
            return

        try:
            self.logger.removeHandler(handler)
        finally:
            handler.close()
            setattr(self, attribute_name, None)
