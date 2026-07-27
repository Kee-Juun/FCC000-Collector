import logging
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options

from core.browser import BrowserAutomation
from core.collector import CollectionWorker
from core.webdriver_factory import (
    CHROMEDRIVER_PATH_ENV,
    ChromeStartupError,
    create_chrome_driver,
)


class WebDriverFactoryTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger(f"webdriver-test-{id(self)}")
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())

    @patch("core.webdriver_factory.webdriver.Chrome")
    def test_uses_selenium_manager_by_default(self, chrome):
        driver = MagicMock()
        driver.capabilities = {
            "browserVersion": "151.0.7922.34",
            "chrome": {"chromedriverVersion": "151.0.7922.12 (build)"},
        }
        chrome.return_value = driver

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(CHROMEDRIVER_PATH_ENV, None)
            result = create_chrome_driver(Options(), self.logger, implicit_wait=30)

        self.assertIs(result, driver)
        chrome.assert_called_once()
        self.assertNotIn("service", chrome.call_args.kwargs)
        driver.implicitly_wait.assert_called_once_with(30)

    @patch("core.webdriver_factory.webdriver.Chrome")
    def test_version_mismatch_becomes_actionable_startup_error(self, chrome):
        chrome.side_effect = SessionNotCreatedException(
            "This version of ChromeDriver only supports Chrome version 114; "
            "Current browser version is 151.0.7922.34"
        )

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(CHROMEDRIVER_PATH_ENV, None)
            with self.assertRaises(ChromeStartupError) as raised:
                create_chrome_driver(Options(), self.logger)

        message = str(raised.exception)
        self.assertIn("not compatible", message)
        self.assertIn(CHROMEDRIVER_PATH_ENV, message)
        self.assertIn("Chrome version 114", message)

    @patch("core.webdriver_factory.webdriver.Chrome")
    def test_generic_chrome_crash_is_not_mislabeled_as_version_mismatch(self, chrome):
        chrome.side_effect = SessionNotCreatedException(
            "Chrome failed to start: crashed; DevToolsActivePort file doesn't exist"
        )

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(CHROMEDRIVER_PATH_ENV, None)
            with self.assertRaises(ChromeStartupError) as raised:
                create_chrome_driver(Options(), self.logger)

        message = str(raised.exception)
        self.assertIn("could not start Google Chrome", message)
        self.assertNotIn("not compatible", message)

    @patch("core.webdriver_factory.webdriver.Chrome")
    def test_explicit_offline_driver_path_is_supported(self, chrome):
        driver = MagicMock()
        driver.capabilities = {}
        chrome.return_value = driver

        driver_path = Path(r"C:\offline-driver\chromedriver.exe")
        with patch("core.webdriver_factory.Path.is_file", return_value=True):
            with patch.dict(
                os.environ,
                {CHROMEDRIVER_PATH_ENV: str(driver_path)},
                clear=False,
            ):
                result = create_chrome_driver(Options(), self.logger)

        self.assertIs(result, driver)
        self.assertIn("service", chrome.call_args.kwargs)


class FailFastTests(unittest.TestCase):
    def test_fcc_browser_does_not_turn_startup_failure_into_empty_results(self):
        automation = BrowserAutomation(logging.getLogger("browser-fail-fast"), headless=True)
        with patch.object(
            automation,
            "_create_driver",
            side_effect=ChromeStartupError("driver mismatch"),
        ):
            with self.assertRaises(ChromeStartupError):
                automation.extract_pdf_links("https://example.invalid")

    def test_worker_closes_run_log_handler_after_startup_failure(self):
        logger = logging.getLogger(f"collector-cleanup-{id(self)}")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.NullHandler())

        mock_handler = MagicMock(spec=logging.FileHandler)
        mock_handler.level = logging.INFO
        with patch("core.collector.Path.mkdir"), patch(
            "core.collector.logging.FileHandler",
            return_value=mock_handler,
        ):
            worker = CollectionWorker(
                ["2026/07/17"],
                Path.cwd(),
                logger,
            )
            worker.duplicate_checker.load_existing_documents_by_date_range = MagicMock(
                side_effect=ChromeStartupError("driver mismatch")
            )

            worker.run()

        self.assertNotIn(mock_handler, logger.handlers)
        self.assertIsNone(worker.run_file_handler)
        mock_handler.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
