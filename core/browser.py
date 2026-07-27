"""Browser automation for web scraping."""

import logging
import time
import re
from pathlib import Path
from typing import List, Dict
from urllib.parse import urljoin, urlparse
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from core.webdriver_factory import ChromeStartupError, create_chrome_driver
from utils.config import BROWSER_TIMEOUT, CHROME_OPTIONS


class BrowserAutomation:
    """Handles browser automation for PDF link extraction."""
    
    def __init__(self, logger: logging.Logger, headless: bool = False):
        """
        Initialize browser automation.
        
        Args:
            logger: Logger instance
            headless: Run browser in headless mode (default False to avoid detection)
        """
        self.logger = logger
        self.headless = headless
        self.driver = None
    
    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome driver."""
        chrome_options = Options()
        
        if self.headless:
            for option in CHROME_OPTIONS:
                chrome_options.add_argument(option)
        
        # Add user agent to avoid detection
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Additional options for better compatibility
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        
        driver = create_chrome_driver(chrome_options, self.logger)
        
        # Execute script to remove webdriver property
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
        
        return driver
    
    def extract_pdf_links(self, url: str) -> List[Dict]:
        """
        Extract PDF links from a webpage.
        
        Args:
            url: URL to scrape
            
        Returns:
            List of dictionaries containing PDF link information
        """
        self.logger.info(f"Navigating to: {url}")
        
        try:
            self.driver = self._create_driver()
            self.driver.get(url)
            
            # Wait for page to load completely
            WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Wait for page to be fully loaded (including JavaScript)
            WebDriverWait(self.driver, BROWSER_TIMEOUT).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )
            
            # Scroll to bottom to trigger lazy loading
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Additional wait for dynamic content
            time.sleep(3)
            
            # Check if page loaded successfully (not an error page)
            page_title = self.driver.title
            page_source = self.driver.page_source
            
            # Check for "Page Not Found" errors (invalid date)
            if "Page Not Found" in page_title:
                self.logger.warning(f"Page Not Found detected. Page title: {page_title}")
                self.logger.warning("This usually means the selected date is invalid or too recent.")
                return []
            
            # Check for Chrome error pages
            if "ERR_" in page_source or "This site can't be reached" in page_source or "neterror" in page_source.lower():
                self.logger.error("Chrome error page detected. The website may be blocking automated access or there's a network issue.")
                self.logger.error(f"Page title: {page_title}")
                self.logger.error("Error: ERR_HTTP2_PROTOCOL_ERROR detected")
                self.logger.error("Possible solutions:")
                self.logger.error("1. Try running without headless mode (set headless=True)")
                self.logger.error("2. Check network connectivity")
                self.logger.error("3. The site may be blocking automated browsers")
                
                # Save error page for debugging
                try:
                    debug_file = Path('debug_page_source.html')
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(page_source)
                    self.logger.info(f"Saved error page to {debug_file} for debugging")
                except Exception as e:
                    self.logger.debug(f"Could not save debug file: {e}")
                
                return []
            
            self.logger.info(f"Page source length: {len(page_source)}")
            self.logger.info(f"Page title: {page_title}")
            
            # Debug: Save page source for analysis
            try:
                debug_file = Path('debug_page_source.html')
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                self.logger.info(f"Saved page source to {debug_file} for debugging")
            except Exception as e:
                self.logger.debug(f"Could not save debug file: {e}")
            
            # Parse with BeautifulSoup - this should find the links
            soup = BeautifulSoup(page_source, 'html.parser')
            pdf_links_soup = self._parse_pdf_links(soup, url)
            
            # Also try Selenium method
            pdf_links_selenium = self._find_pdf_links_selenium(url)
            
            # Try XPath method as well
            pdf_links_xpath = self._find_pdf_links_xpath(url)
            
            # Try regex method as final fallback
            pdf_links_regex = self._find_pdf_links_regex(page_source, url)
            
            # Try direct URL extraction (simplest method)
            pdf_links_direct = self._extract_pdf_urls_direct(page_source, url)
            
            # Combine and deduplicate
            all_links = {}
            for link in pdf_links_soup + pdf_links_selenium + pdf_links_xpath + pdf_links_regex + pdf_links_direct:
                all_links[link['url']] = link
            
            pdf_links = list(all_links.values())
            
            self.logger.info(f"Found {len(pdf_links)} PDF links")
            if len(pdf_links) == 0:
                # Debug: Check if page source contains PDF references
                if '.pdf' in page_source.lower():
                    self.logger.warning("Page source contains '.pdf' but no links were extracted")
                    # Try to find any href with pdf
                    test_soup = BeautifulSoup(page_source, 'html.parser')
                    all_hrefs = [a.get('href', '') for a in test_soup.find_all('a', href=True)]
                    pdf_hrefs = [h for h in all_hrefs if '.pdf' in h.lower()]
                    self.logger.info(f"Found {len(pdf_hrefs)} hrefs containing '.pdf' in page source")
                    if pdf_hrefs:
                        self.logger.info(f"Sample PDF hrefs: {pdf_hrefs[:3]}")
            
            return pdf_links
            
        except ChromeStartupError:
            # A startup failure is fatal for the whole collection. Returning an
            # empty list here would incorrectly report that the date had no PDFs.
            raise
        except Exception as e:
            self.logger.error(f"Error extracting PDF links: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
        finally:
            self.quit()
    
    def _find_pdf_links_selenium(self, base_url: str) -> List[Dict]:
        """
        Find PDF links using Selenium directly.
        
        Args:
            base_url: Base URL for resolving relative links
            
        Returns:
            List of PDF link dictionaries
        """
        pdf_links = []
        seen_urls = set()
        
        try:
            # Find all anchor tags
            links = self.driver.find_elements(By.TAG_NAME, 'a')
            self.logger.info(f"Found {len(links)} total links on page")
            
            for link in links:
                try:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    # Check if it's a PDF link
                    if not (href.endswith('.pdf') or '.pdf' in href.lower()):
                        continue
                    
                    # Resolve full URL
                    full_url = urljoin(base_url, href)
                    
                    # Skip duplicates
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    # Get link text
                    link_text = link.text.strip()
                    
                    # Extract filename
                    filename = os.path.basename(urlparse(full_url).path)
                    
                    # Use link text or filename as doc number
                    if link_text:
                        doc_number = link_text
                    else:
                        doc_number = filename.replace('.pdf', '').replace('.PDF', '')
                    
                    if doc_number and filename:
                        pdf_links.append({
                            'url': full_url,
                            'doc_number': doc_number,
                            'filename': filename if filename.endswith('.pdf') else f"{filename}.pdf"
                        })
                except Exception as e:
                    self.logger.debug(f"Error processing link: {e}")
                    continue
            
            self.logger.info(f"Found {len(pdf_links)} PDF links via Selenium")
            
        except Exception as e:
            self.logger.error(f"Error in Selenium link finding: {e}")
        
        return pdf_links
    
    def _parse_pdf_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """
        Parse PDF links from BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            
        Returns:
            List of PDF link dictionaries
        """
        pdf_links = []
        seen_urls = set()  # Avoid duplicates
        
        # Find all anchor tags with href - try multiple approaches
        all_links = soup.find_all('a', href=True)
        self.logger.info(f"BeautifulSoup found {len(all_links)} total anchor tags")
        
        for link in all_links:
            href = link.get('href')
            if not href:
                continue
            
            href_lower = href.lower()
            
            # Check if link points to PDF - multiple patterns
            is_pdf = (
                href_lower.endswith('.pdf') or 
                ('.pdf' in href_lower and '/attachments/' in href_lower) or
                ('.pdf' in href_lower and 'docs.fcc.gov' in href_lower)
            )
            
            if not is_pdf:
                continue
            
            # Resolve full URL
            full_url = urljoin(base_url, href)
            
            # Skip if already seen
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            # Extract document information
            link_text = link.get_text(strip=True)
            filename = os.path.basename(urlparse(full_url).path)
            
            # Ensure filename ends with .pdf
            if not filename.lower().endswith('.pdf'):
                if '.pdf' in filename.lower():
                    # Extract the part before .pdf and add .pdf
                    parts = filename.lower().split('.pdf')
                    filename = parts[0] + '.pdf'
                else:
                    filename = filename + '.pdf'
            
            # Use link text or filename as doc number
            if link_text and link_text.strip():
                doc_number = link_text.strip()
            else:
                doc_number = filename.replace('.pdf', '').replace('.PDF', '')
            
            if doc_number and filename:
                pdf_links.append({
                    'url': full_url,
                    'doc_number': doc_number,
                    'filename': filename
                })
        
        self.logger.info(f"Found {len(pdf_links)} PDF links via BeautifulSoup")
        return pdf_links
    
    def _find_pdf_links_xpath(self, base_url: str) -> List[Dict]:
        """
        Find PDF links using XPath.
        
        Args:
            base_url: Base URL for resolving relative links
            
        Returns:
            List of PDF link dictionaries
        """
        pdf_links = []
        seen_urls = set()
        
        try:
            # Find all links with PDF in href using XPath
            xpath_query = "//a[contains(@href, '.pdf')]"
            links = self.driver.find_elements(By.XPATH, xpath_query)
            
            for link in links:
                try:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    full_url = urljoin(base_url, href)
                    
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    link_text = link.text.strip()
                    filename = os.path.basename(urlparse(full_url).path)
                    
                    if not filename.lower().endswith('.pdf'):
                        filename = filename + '.pdf'
                    
                    if link_text:
                        doc_number = link_text
                    else:
                        doc_number = filename.replace('.pdf', '').replace('.PDF', '')
                    
                    if doc_number and filename:
                        pdf_links.append({
                            'url': full_url,
                            'doc_number': doc_number,
                            'filename': filename
                        })
                except Exception as e:
                    self.logger.debug(f"Error processing XPath link: {e}")
                    continue
            
            self.logger.info(f"Found {len(pdf_links)} PDF links via XPath")
            
        except Exception as e:
            self.logger.error(f"Error in XPath link finding: {e}")
        
        return pdf_links
    
    def _find_pdf_links_regex(self, html_source: str, base_url: str) -> List[Dict]:
        """
        Find PDF links using regex pattern matching on HTML source.
        This is a fallback method when other methods fail.
        
        Args:
            html_source: HTML page source
            base_url: Base URL for resolving relative links
            
        Returns:
            List of PDF link dictionaries
        """
        pdf_links = []
        seen_urls = set()
        
        try:
            # Multiple patterns to catch different HTML structures
            patterns = [
                # Pattern 1: Standard <a href="...pdf">text</a>
                r'<a[^>]*href=["\']([^"\']*\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',
                # Pattern 2: href with target and other attributes
                r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                # Pattern 3: Just find any URL with .pdf in it
                r'(https?://[^\s<>"\']+\.pdf)',
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, html_source, re.IGNORECASE | re.DOTALL)
                
                for match in matches:
                    href = match.group(1) if match.lastindex >= 1 else match.group(0)
                    link_text = match.group(2).strip() if match.lastindex >= 2 else ""
                    
                    if not href or '.pdf' not in href.lower():
                        continue
                    
                    # Clean up href (remove any trailing characters that aren't part of URL)
                    href = href.split()[0] if ' ' in href else href
                    href = href.rstrip('.,;:!?')
                    
                    # Resolve full URL
                    full_url = urljoin(base_url, href)
                    
                    # Skip duplicates
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    # Extract filename
                    filename = os.path.basename(urlparse(full_url).path)
                    
                    # Ensure filename ends with .pdf
                    if not filename.lower().endswith('.pdf'):
                        if '.pdf' in filename.lower():
                            parts = filename.lower().split('.pdf')
                            filename = parts[0] + '.pdf'
                        else:
                            filename = filename + '.pdf'
                    
                    # Use link text or filename as doc number
                    if link_text:
                        # Clean HTML tags from link text
                        link_text_clean = re.sub(r'<[^>]+>', '', link_text).strip()
                        doc_number = link_text_clean if link_text_clean else filename.replace('.pdf', '')
                    else:
                        doc_number = filename.replace('.pdf', '').replace('.PDF', '')
                    
                    if doc_number and filename:
                        pdf_links.append({
                            'url': full_url,
                            'doc_number': doc_number,
                            'filename': filename
                        })
            
            self.logger.info(f"Found {len(pdf_links)} PDF links via regex")
            
        except Exception as e:
            self.logger.error(f"Error in regex link finding: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        return pdf_links
    
    def _extract_pdf_urls_direct(self, html_source: str, base_url: str) -> List[Dict]:
        """
        Directly extract PDF URLs from HTML source using simple pattern matching.
        This is the most basic but reliable method.
        
        Args:
            html_source: HTML page source
            base_url: Base URL for resolving relative links
            
        Returns:
            List of PDF link dictionaries
        """
        pdf_links = []
        seen_urls = set()
        
        try:
            # Find all URLs that contain .pdf - very simple pattern
            # Pattern: https://docs.fcc.gov/public/attachments/...pdf or any URL ending in .pdf
            url_pattern = r'(https?://[^\s<>"\']+\.pdf)'
            matches = re.finditer(url_pattern, html_source, re.IGNORECASE)
            
            for match in matches:
                full_url = match.group(1).strip()
                
                # Clean up URL (remove any trailing punctuation that might have been captured)
                full_url = full_url.rstrip('.,;:!?)\'"')
                
                # Skip if already seen
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                
                # Extract filename
                filename = os.path.basename(urlparse(full_url).path)
                
                # Use filename as doc number
                doc_number = filename.replace('.pdf', '').replace('.PDF', '')
                
                if doc_number and filename:
                    pdf_links.append({
                        'url': full_url,
                        'doc_number': doc_number,
                        'filename': filename
                    })
            
            self.logger.info(f"Found {len(pdf_links)} PDF links via direct URL extraction")
            
        except Exception as e:
            self.logger.error(f"Error in direct URL extraction: {e}")
        
        return pdf_links
    
    def quit(self):
        """Close browser driver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None

