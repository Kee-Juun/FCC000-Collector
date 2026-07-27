"""Shared Chrome WebDriver startup with automatic version matching."""

import logging
import os
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


CHROMEDRIVER_PATH_ENV = "FCC000_CHROMEDRIVER_PATH"


class ChromeStartupError(RuntimeError):
    """Raised when a compatible Chrome/ChromeDriver session cannot be created."""


def _startup_error_message(error: Exception, configured_path: Optional[Path]) -> str:
    details = " ".join(str(error).split())
    mismatch = (
        "only supports Chrome version" in details
        or "This version of ChromeDriver" in details
        or "current browser version is" in details.lower()
    )

    if configured_path:
        source = f"the driver configured in {CHROMEDRIVER_PATH_ENV} ({configured_path})"
    else:
        source = "Selenium Manager's automatically selected driver"

    if mismatch:
        reason = f"{source} is not compatible with the installed Google Chrome version."
    else:
        reason = f"{source} could not start Google Chrome."

    return (
        f"Chrome could not be started: {reason} "
        "Check that Chrome is installed and that the network/proxy permits Selenium "
        "Manager to obtain the matching ChromeDriver. On an offline machine, set "
        f"{CHROMEDRIVER_PATH_ENV} to a compatible local chromedriver.exe. "
        f"Technical details: {details}"
    )


def create_chrome_driver(
    options: Options,
    logger: logging.Logger,
    implicit_wait: Optional[int] = None,
) -> webdriver.Chrome:
    """Create Chrome using Selenium Manager or an explicitly configured driver.

    Selenium Manager detects the installed Chrome version and selects a matching
    driver. This avoids reusing webdriver-manager's stale ChromeDriver cache.
    """
    configured_value = os.environ.get(CHROMEDRIVER_PATH_ENV, "").strip().strip('"')
    configured_path = Path(configured_value).expanduser() if configured_value else None

    if configured_path and not configured_path.is_file():
        raise ChromeStartupError(
            f"Chrome could not be started: {CHROMEDRIVER_PATH_ENV} points to a file "
            f"that does not exist: {configured_path}"
        )

    try:
        if configured_path:
            logger.info(f"Starting Chrome with configured driver: {configured_path}")
            driver = webdriver.Chrome(
                service=Service(str(configured_path)),
                options=options,
            )
        else:
            logger.info("Starting Chrome with Selenium Manager version matching")
            driver = webdriver.Chrome(options=options)

        if implicit_wait is not None:
            driver.implicitly_wait(implicit_wait)

        capabilities = driver.capabilities or {}
        browser_version = capabilities.get("browserVersion", "unknown")
        chrome_details = capabilities.get("chrome", {}) or {}
        driver_version = str(chrome_details.get("chromedriverVersion", "unknown")).split()[0]
        logger.info(
            f"Chrome session ready: browser {browser_version}, driver {driver_version}"
        )
        return driver

    except ChromeStartupError:
        raise
    except (WebDriverException, OSError) as error:
        message = _startup_error_message(error, configured_path)
        logger.error(message)
        raise ChromeStartupError(message) from error
