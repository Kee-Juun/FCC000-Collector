"""Online duplicate checking using IRT database."""

import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.webdriver_factory import ChromeStartupError, create_chrome_driver
from utils.config import BROWSER_TIMEOUT, CHROME_OPTIONS


IRT_SERVER_DOWN_MESSAGE = (
    "There is some error in the application : Some error occurred in the application.\n"
    "Please raise a webstar to contact Engineering/Admin team for resolution"
)


class IRTServerUnavailableError(RuntimeError):
    """Raised when IRT shows the application/server-down error page."""


class OnlineDuplicateChecker:
    """Checks for duplicates in online IRT database."""

    IRT_HOME_URL = "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/"
    COURT_CODE = "FDFCC000"

    DATE_FROM_XPATH = '//*[@id="receivedDateandTimeSearchFrom"]'
    DATE_TO_XPATH = '//*[@id="receivedDateandTimeSearchTo"]'
    SEARCH_BUTTON_XPATH = '//*[@id="search"]'
    SEARCH_TABLE_XPATH = '//*[@id="searchTable"]'
    SEARCH_TABLE_BODY_XPATH = '//*[@id="searchTable"]/tbody'

    IRT_RESULTS_TIMEOUT = 120
    IRT_STARTUP_ATTEMPTS = 3

    DOC_ID_PATTERN = re.compile(
        r"(DOC-\d+[A-Z0-9]*|DA-\d+-\d+[A-Z0-9]*|FCC-\d+-\d+[A-Z0-9]*)",
        re.IGNORECASE,
    )

    def __init__(self, logger: logging.Logger, headless: bool = True):
        self.logger = logger
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self._initialized = False
        self._court_code_set = False
        self._last_bulk_load_success = False

    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome driver."""
        options = Options()
        if self.headless:
            for option in CHROME_OPTIONS:
                options.add_argument(option)

        return create_chrome_driver(
            options,
            self.logger,
            implicit_wait=BROWSER_TIMEOUT,
        )

    def _initialize(self):
        """Initialize browser and navigate to search page."""
        if self._initialized and self.driver:
            return

        search_inventory_xpath = '//*[@id="menu"]/table/thead/tr/td[3]/h3/a'
        file_name_field_xpath = '//*[@id="originalFileNameSearch"]'

        if not self.driver:
            self.driver = self._create_driver()

        last_error: Optional[Exception] = None

        for attempt in range(1, self.IRT_STARTUP_ATTEMPTS + 1):
            try:
                self.logger.info(
                    f"IRT startup attempt {attempt}/{self.IRT_STARTUP_ATTEMPTS}: "
                    f"opening Home Page: {self.IRT_HOME_URL}"
                )
                self.driver.get(self.IRT_HOME_URL)
                time.sleep(2)

                if self._is_irt_server_down_page():
                    raise IRTServerUnavailableError(IRT_SERVER_DOWN_MESSAGE)

                self.logger.info("Clicking Search Inventory...")
                search_button = WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                    EC.element_to_be_clickable((By.XPATH, search_inventory_xpath))
                )
                search_button.click()
                time.sleep(2)

                if self._is_irt_server_down_page():
                    raise IRTServerUnavailableError(IRT_SERVER_DOWN_MESSAGE)

                WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                    EC.presence_of_element_located((By.XPATH, file_name_field_xpath))
                )

                court_code_xpath = '//*[@id="courtSearch"]'
                court_code_field = self.driver.find_element(By.XPATH, court_code_xpath)
                court_code_field.clear()
                court_code_field.send_keys(self.COURT_CODE)

                self._court_code_set = True
                self._initialized = True
                return

            except IRTServerUnavailableError as e:
                last_error = e
                self.logger.warning(
                    f"IRT startup attempt {attempt}/{self.IRT_STARTUP_ATTEMPTS} "
                    "found the IRT application error page."
                )
            except Exception as e:
                last_error = e
                if self._is_irt_server_down_page():
                    last_error = IRTServerUnavailableError(IRT_SERVER_DOWN_MESSAGE)
                    self.logger.warning(
                        f"IRT startup attempt {attempt}/{self.IRT_STARTUP_ATTEMPTS} "
                        "failed and the IRT application error page is visible."
                    )
                else:
                    self.logger.warning(
                        f"IRT startup attempt {attempt}/{self.IRT_STARTUP_ATTEMPTS} "
                        f"failed: {type(e).__name__}: {e!r}"
                    )

            if attempt < self.IRT_STARTUP_ATTEMPTS:
                self.logger.info("Refreshing IRT page before retrying...")
                try:
                    self.driver.refresh()
                    time.sleep(2)
                except Exception as refresh_error:
                    self.logger.warning(
                        f"Unable to refresh IRT page before retry: "
                        f"{type(refresh_error).__name__}: {refresh_error!r}"
                    )

        self._court_code_set = False
        self._initialized = False

        if isinstance(last_error, IRTServerUnavailableError):
            raise last_error

        raise IRTServerUnavailableError(IRT_SERVER_DOWN_MESSAGE)

    @classmethod
    def normalize_document_id(cls, filename: str) -> str:
        """
        Extract the base FCC document ID.

        Examples:
            DOC-421093A1.pdf -> DOC-421093A1
            LDC_SMD_DOC-421093A1_E2E.pdf -> DOC-421093A1
            DA-26-415A1.pdf -> DA-26-415A1
        """
        if not filename:
            return ""

        text = filename.upper().strip()
        match = cls.DOC_ID_PATTERN.search(text)
        if match:
            return match.group(1).upper()

        return text.replace(".PDF", "").strip()

    @staticmethod
    def _format_irt_date(date_str: str) -> str:
        """
        Convert YYYY/MM/DD to MM-DD-YYYY.
        If already MM-DD-YYYY, return as-is.
        """
        date_str = (date_str or "").strip()

        if "/" in date_str:
            year, month, day = date_str.split("/")
            return f"{month}-{day}-{year}"

        return date_str

    def _clear_field_if_present(self, xpath: str):
        try:
            field = self.driver.find_element(By.XPATH, xpath)
            field.clear()
        except Exception:
            pass

    @staticmethod
    def _normalize_page_text(text: str) -> str:
        return " ".join((text or "").split()).lower()

    def _is_irt_server_down_page(self) -> bool:
        """Return True when IRT displays the known maintenance/error page."""
        if not self.driver:
            return False

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_text = ""

        try:
            page_source = self.driver.page_source
        except Exception:
            page_source = ""

        page_text = self._normalize_page_text(f"{body_text} {page_source}")
        server_down_text = self._normalize_page_text(IRT_SERVER_DOWN_MESSAGE)

        return server_down_text in page_text or (
            "there is some error in the application" in page_text
            and "please raise a webstar" in page_text
        )

    def _wait_for_irt_results_ready(self, timeout: int = IRT_RESULTS_TIMEOUT) -> bool:
        """
        Wait until IRT result table is actually ready.

        This waits for one of these:
            1. Table has a row with a non-empty File Name column.
            2. Table explicitly says no matching records/no data.
            3. Timeout occurs.
        """
        def table_ready(driver):
            try:
                table_body = driver.find_element(By.XPATH, self.SEARCH_TABLE_BODY_XPATH)
                rows = table_body.find_elements(By.TAG_NAME, "tr")

                if not rows:
                    return False

                table_text = table_body.text.strip().lower()

                no_result_markers = [
                    "no matching records",
                    "no data available",
                    "no records found",
                ]

                if any(marker in table_text for marker in no_result_markers):
                    return True

                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2 and cells[1].text.strip():
                        return True

                return False

            except Exception:
                return False

        WebDriverWait(self.driver, timeout).until(table_ready)
        return True

    def _click_search_and_wait_for_results(self):
        """Click IRT Search and wait until the table is populated or confirmed empty."""
        search_btn = self.driver.find_element(By.XPATH, self.SEARCH_BUTTON_XPATH)
        search_btn.click()

        self.logger.info("Waiting for IRT result table to finish loading...")
        WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
            EC.presence_of_element_located((By.XPATH, self.SEARCH_TABLE_XPATH))
        )
        self._wait_for_irt_results_ready(timeout=self.IRT_RESULTS_TIMEOUT)

        # Small stabilization pause after table readiness
        time.sleep(1)

    def load_existing_documents_by_date_range(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, List[Dict]]:
        """
        Search IRT once by received date range and collect existing FCC documents.

        Returns:
            Dict mapping normalized document ID to one or more full IRT records.
        """
        existing_documents: Dict[str, List[Dict]] = {}
        self._last_bulk_load_success = False

        try:
            if not self._initialized:
                self._initialize()

            start_date_irt = self._format_irt_date(start_date)
            end_date_irt = self._format_irt_date(end_date)

            self.logger.info(
                f"Loading existing IRT documents for received date range "
                f"{start_date_irt} to {end_date_irt}"
            )

            # Make sure filename search does not narrow the date-range report.
            self._clear_field_if_present('//*[@id="originalFileNameSearch"]')

            court_code_field = self.driver.find_element(By.XPATH, '//*[@id="courtSearch"]')
            court_code_field.clear()
            court_code_field.send_keys(self.COURT_CODE)

            date_from = WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, self.DATE_FROM_XPATH))
            )
            date_to = self.driver.find_element(By.XPATH, self.DATE_TO_XPATH)

            date_from.clear()
            date_from.send_keys(start_date_irt)

            date_to.clear()
            date_to.send_keys(end_date_irt)

            self._click_search_and_wait_for_results()

            while True:
                documents_on_page = self._extract_documents_from_current_results_page()

                # If table was slow and first extraction produced nothing,
                # retry once before accepting zero results.
                if not documents_on_page:
                    self.logger.warning(
                        "IRT table returned 0 normalized document IDs after load; "
                        "waiting briefly and retrying current page once..."
                    )
                    time.sleep(10)
                    documents_on_page = self._extract_documents_from_current_results_page()

                for doc_id, records in documents_on_page.items():
                    existing_documents.setdefault(doc_id, []).extend(records)

                if not self._go_to_next_irt_results_page():
                    break

            self._last_bulk_load_success = True
            total_records = sum(len(records) for records in existing_documents.values())

            self.logger.info(
                f"Loaded {len(existing_documents)} normalized document ID(s) "
                f"from IRT ({total_records} record(s))"
            )

            if not existing_documents:
                self.logger.warning(
                    "IRT duplicate report completed but returned 0 normalized document IDs. "
                    "If records were expected, verify the IRT date range, File Name column, "
                    "and table loading behavior."
                )

            return existing_documents

        except ChromeStartupError:
            self._last_bulk_load_success = False
            raise
        except IRTServerUnavailableError:
            self.logger.error(f"IRT startup failed after {self.IRT_STARTUP_ATTEMPTS} attempts.")
            self._last_bulk_load_success = False
            raise
        except Exception as e:
            self.logger.error(
                f"Error loading existing documents by date range: {type(e).__name__}: {e!r}"
            )
            self._last_bulk_load_success = False
            return existing_documents

    def _parse_irt_received_datetime(self, received_date: str) -> Optional[datetime]:
        """Parse an IRT Received Date value into a comparable datetime."""
        received_date = (received_date or "").strip()
        if not received_date:
            return None

        normalized_date = " ".join(received_date.split())
        date_formats = (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%m/%d/%Y",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m-%d-%Y",
            "%m-%d-%Y %I:%M %p",
            "%m-%d-%Y %I:%M:%S %p",
            "%m-%d-%Y %H:%M",
            "%m-%d-%Y %H:%M:%S",
        )

        for date_format in date_formats:
            try:
                return datetime.strptime(normalized_date, date_format)
            except ValueError:
                continue

        self.logger.debug(
            f"Unable to parse IRT Received Date value: {received_date!r}"
        )
        return None

    def get_most_recent_received_record(
        self,
        start_date: str,
        end_date: str,
    ) -> Optional[Dict]:
        """
        Return the IRT record with the most recent Received Date in a date range.
        """
        existing_documents = self.load_existing_documents_by_date_range(
            start_date=start_date,
            end_date=end_date,
        )

        if not getattr(self, "_last_bulk_load_success", False):
            self.logger.warning(
                "Unable to determine the most recent IRT record because "
                "the date-range load did not complete successfully."
            )
            return None

        all_records = [
            record
            for records in existing_documents.values()
            for record in records
        ]

        if not all_records:
            self.logger.info(
                "No IRT records were found when looking up the most recent "
                f"record for received date range {start_date} to {end_date}"
            )
            return None

        latest_record = None
        latest_received_dt = None

        for record in all_records:
            received_dt = self._parse_irt_received_datetime(
                record.get("Received Date", "")
            )
            if received_dt is None:
                continue

            if latest_received_dt is None or received_dt > latest_received_dt:
                latest_received_dt = received_dt
                latest_record = record

        if latest_record:
            self.logger.info(
                "Most recent IRT record found for received date range "
                f"{start_date} to {end_date}: "
                f"LNI={latest_record.get('LNI', 'N/A')}, "
                f"Received Date={latest_record.get('Received Date', 'N/A')}"
            )
            return latest_record

        self.logger.warning(
            "IRT records were found for received date range "
            f"{start_date} to {end_date}, but none had a parseable Received Date."
        )
        return None

    def _extract_documents_from_current_results_page(self) -> Dict[str, List[Dict]]:
        """Read current IRT results page and extract records keyed by normalized document ID."""
        documents: Dict[str, List[Dict]] = {}

        try:
            row_count, records = self._extract_duplicate_records_from_current_table()

            self.logger.info(f"IRT result rows found on current page: {row_count}")

            for record in records:
                file_name = record.get("File Name", "")
                normalized_id = self.normalize_document_id(file_name)

                self.logger.debug(
                    f"IRT file name cell: {file_name!r}; normalized ID: {normalized_id!r}"
                )

                if normalized_id:
                    documents.setdefault(normalized_id, []).append(record)

            self.logger.info(
                f"Read {len(documents)} normalized document ID(s) from current IRT page"
            )
            return documents

        except Exception as e:
            self.logger.warning(
                f"Error reading IRT result table: {type(e).__name__}: {e!r}"
            )
            return documents

    def _go_to_next_irt_results_page(self) -> bool:
        """Move to the next IRT results page if table pagination exists."""
        possible_next_selectors = [
            '//*[@id="searchTable_next"]',
            '//a[contains(@class, "paginate_button") and normalize-space()="Next"]',
            '//li[contains(@class, "paginate_button next")]//a',
        ]

        # Avoid spending the full implicit wait on missing pagination controls.
        # Some IRT result tables render the entire date range on one page and do
        # not show a Next button at all.
        self.driver.implicitly_wait(0)
        try:
            for selector in possible_next_selectors:
                try:
                    next_buttons = self.driver.find_elements(By.XPATH, selector)
                    if not next_buttons:
                        continue

                    next_btn = next_buttons[0]
                    class_attr = (next_btn.get_attribute("class") or "").lower()
                    parent_class = ""

                    try:
                        parent_class = (
                            next_btn.find_element(By.XPATH, "./ancestor::li[1]").get_attribute("class")
                            or ""
                        ).lower()
                    except Exception:
                        pass

                    if "disabled" in class_attr or "disabled" in parent_class:
                        return False

                    if not next_btn.is_displayed() or not next_btn.is_enabled():
                        return False

                    before_text = self.driver.find_element(
                        By.XPATH, self.SEARCH_TABLE_BODY_XPATH
                    ).text

                    next_btn.click()

                    WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                        lambda d: d.find_element(By.XPATH, self.SEARCH_TABLE_BODY_XPATH).text
                        != before_text
                    )

                    self._wait_for_irt_results_ready(timeout=self.IRT_RESULTS_TIMEOUT)
                    time.sleep(1)
                    return True

                except Exception:
                    continue
        finally:
            self.driver.implicitly_wait(BROWSER_TIMEOUT)

        return False

    def get_duplicate_records(
        self,
        original_filename: str,
        existing_documents: Dict[str, List[Dict]],
    ) -> List[Dict]:
        """
        Return duplicate IRT records for an FCC original filename using the cached map.
        """
        normalized_id = self.normalize_document_id(original_filename)
        if not normalized_id:
            return []

        return existing_documents.get(normalized_id, [])

    def check_duplicate(self, filename: str) -> Tuple[bool, List[Dict]]:
        """
        Fallback: check if a file exists in the online database using one-by-one search.

        This fallback searches by normalized base document ID, not the renamed download filename.
        """
        try:
            if not self._initialized:
                self._initialize()

            normalized_id = self.normalize_document_id(filename)
            search_value = normalized_id or filename
            search_pattern = f"*{search_value}*"

            self.logger.info(f"Searching for duplicate by base document ID: {search_pattern}")

            # Clear date fields so fallback filename search is not accidentally narrowed.
            self._clear_field_if_present(self.DATE_FROM_XPATH)
            self._clear_field_if_present(self.DATE_TO_XPATH)

            court_code_field = self.driver.find_element(By.XPATH, '//*[@id="courtSearch"]')
            court_code_field.clear()
            court_code_field.send_keys(self.COURT_CODE)

            file_name_field_xpath = '//*[@id="originalFileNameSearch"]'
            file_name_field = self.driver.find_element(By.XPATH, file_name_field_xpath)
            file_name_field.clear()
            file_name_field.send_keys(search_pattern)

            self._click_search_and_wait_for_results()

            _, duplicate_records = self._extract_duplicate_records_from_current_table()

            if duplicate_records:
                self.logger.info(
                    f"Found {len(duplicate_records)} duplicate record(s) for {search_value}"
                )
                return True, duplicate_records

            self.logger.info(f"No duplicates found for {search_value}")
            return False, []

        except IRTServerUnavailableError:
            raise
        except Exception as e:
            self.logger.error(f"Error checking duplicate for {filename}: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return False, []

    def _extract_duplicate_records_from_current_table(self) -> Tuple[int, List[Dict]]:
        """
        Extract IRT result rows from the current table page.

        Uses one JavaScript DOM pass for speed, with a Selenium fallback if the
        page structure changes unexpectedly.
        """
        table_body = self.driver.find_element(By.XPATH, self.SEARCH_TABLE_BODY_XPATH)

        try:
            extraction = self.driver.execute_script(
                """
                const tbody = arguments[0];
                const table = tbody.closest("table");
                const textOf = (cells, index) => {
                    if (index >= cells.length || !cells[index]) {
                        return "";
                    }
                    return (cells[index].textContent || "").trim();
                };
                const normalizeHeader = (value) =>
                    (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const headerTexts = table
                    ? Array.from(table.querySelectorAll("thead tr:last-child th")).map(
                        (th) => normalizeHeader(th.textContent)
                    )
                    : [];
                const headerIndex = (headerName, fallbackIndex) => {
                    const foundIndex = headerTexts.indexOf(normalizeHeader(headerName));
                    return foundIndex >= 0 ? foundIndex : fallbackIndex;
                };

                const lniIndex = headerIndex("LNI", 0);
                const fileNameIndex = headerIndex("File Name", 1);
                const decidedDateIndex = headerIndex("Decided Date", 5);
                const receivedDateIndex = headerIndex("Received Date", 6);
                const routeIndex = headerIndex("Route", 14);
                const sourceDetailIndex = headerIndex("Source Detail", 15);

                const rows = Array.from(tbody.querySelectorAll("tr"));
                const records = [];

                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll("td"));
                    if (cells.length < 2) {
                        continue;
                    }

                    const fileName = textOf(cells, fileNameIndex);
                    if (!fileName) {
                        continue;
                    }

                    records.push({
                        "LNI": textOf(cells, lniIndex),
                        "File Name": fileName,
                        "Decided Date": textOf(cells, decidedDateIndex),
                        "Received Date": textOf(cells, receivedDateIndex),
                        "Route": textOf(cells, routeIndex),
                        "Source Detail": textOf(cells, sourceDetailIndex),
                    });
                }

                return {
                    rowCount: rows.length,
                    records: records,
                };
                """,
                table_body,
            )

            row_count = int(extraction.get("rowCount", 0))
            records = extraction.get("records", []) or []
            return row_count, records

        except Exception as e:
            self.logger.warning(
                "JavaScript IRT table extraction failed; falling back to Selenium row reads. "
                f"{type(e).__name__}: {e!r}"
            )
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            return len(rows), self._extract_duplicate_records(rows)

    def _extract_duplicate_records(self, rows) -> List[Dict]:
        """
        Extract duplicate record information from table rows.

        Columns:
            LNI: td[1] / index 0
            File Name: td[2] / index 1
            Decided Date: td[6] / index 5
            Received Date: td[7] / index 6
            Route: td[15] / index 14
            Source Detail: td[16] / index 15
        """
        duplicate_records = []

        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")

                if len(cells) < 2:
                    continue

                file_name = cells[1].text.strip()
                lni = cells[0].text.strip()

                # Ignore DataTables "No matching records" rows or empty rows.
                if not file_name:
                    continue

                record = {
                    "LNI": lni,
                    "File Name": file_name,
                    "Decided Date": cells[5].text.strip() if len(cells) > 5 else "",
                    "Received Date": cells[6].text.strip() if len(cells) > 6 else "",
                    "Route": cells[14].text.strip() if len(cells) > 14 else "",
                    "Source Detail": cells[15].text.strip() if len(cells) > 15 else "",
                }
                duplicate_records.append(record)

            except Exception as e:
                self.logger.warning(f"Error extracting record from row: {e}")
                continue

        return duplicate_records

    def quit(self):
        """Close browser driver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None
                self._initialized = False
                self._court_code_set = False
