# url_processor.py
import logging
# import requests # No longer needed for fetching
import trafilatura
import validators
from urllib.parse import urlparse
import socket
import ipaddress

# --- Playwright Import ---
# Ensure you have run: pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Import constant from prompts
from .prompts import MAX_INPUT_CHARS

# --- URL Validation (SSRF Protection) ---
# This function remains unchanged as requested.
def is_safe_url(url_string):
    """Validate URL format and check for SSRF risks."""
    try:
        if not isinstance(url_string, str) or not url_string:
            logging.warning("URL Validation failed: Input is not a valid string.")
            return False

        # 1. Basic URL structure validation using validators library
        if not validators.url(url_string):
            logging.warning(f"URL Validation failed (format): {url_string}")
            return False

        # 2. Parse URL
        parsed_url = urlparse(url_string)

        # 3. Check scheme - only allow http/https
        if parsed_url.scheme not in ['http', 'https']:
            logging.warning(f"URL Validation failed (scheme not http/https): {parsed_url.scheme}")
            return False

        # 4. Resolve hostname and check IP address
        hostname = parsed_url.hostname # Use .hostname which handles ports etc.
        if not hostname:
            logging.warning(f"URL Validation failed (no hostname): {url_string}")
            return False

        resolved_ip_str = "N/A" # For logging
        try:
            # Set timeout for DNS resolution
            socket.setdefaulttimeout(5.0) # 5 second timeout for DNS
            # Use getaddrinfo for better IPv6 support
            addrinfo = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC) # Allow IPv4 or IPv6
            if not addrinfo: # Check if resolution returned anything
                raise socket.gaierror(f"No address associated with hostname: {hostname}")

            resolved_ip_str = addrinfo[0][4][0] # Get the first resolved IP address string
            ip_addr = ipaddress.ip_address(resolved_ip_str)

            # Check if IP is private, loopback, link-local, multicast, or unspecified/reserved
            if not ip_addr.is_global or ip_addr.is_private or ip_addr.is_loopback or ip_addr.is_link_local or ip_addr.is_multicast or ip_addr.is_reserved or ip_addr.is_unspecified:
                logging.warning(f"URL Validation failed (unsafe/non-global IP): {hostname} -> {resolved_ip_str}")
                return False
        except socket.gaierror as e:
            logging.warning(f"URL Validation failed (DNS resolution error for {hostname}): {e}")
            return False
        except socket.timeout:
             logging.warning(f"URL Validation failed (DNS resolution timeout for {hostname})")
             return False
        except ValueError:
             # This might happen if resolved_ip_str isn't a valid IP format somehow
             logging.warning(f"URL Validation failed (Invalid IP format resolved): {resolved_ip_str}")
             return False
        finally:
            socket.setdefaulttimeout(None) # Reset default timeout

        # If all checks pass
        logging.info(f"URL is structurally safe: {url_string} (Resolved hostname {hostname} to public IP: {resolved_ip_str})")
        return True

    except Exception as e:
        # Catch any unexpected errors during validation itself
        logging.error(f"Unexpected error during URL validation for '{url_string}': {e}", exc_info=True)
        return False

# --- URL Fetching and Content Extraction (using Playwright) ---
# Function name and return signature remain the same
def fetch_and_extract_url_content(url):
    """
    Fetches URL content using a headless browser (Playwright), executes JavaScript,
    and extracts main text using Trafilatura.
    Returns tuple: (extracted_text, was_truncated)
    Raises specific standard exceptions on failure (ConnectionError, TimeoutError, ValueError, RuntimeError).
    """
    # Standard User Agent
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    browser_timeout = 90 * 1000 # 90 seconds in milliseconds

    extracted_text = ""
    was_truncated = False
    html_content = ""
    page = None
    context = None
    browser = None

    logging.info(f"Attempting Playwright fetch for URL: {url}") # LOG START

    try:
        logging.info("Initializing Playwright...") # LOG BEFORE with
        with sync_playwright() as p:
            logging.info("Playwright initialized. Launching browser...") # LOG AFTER with
            # --- Launch Browser ---
            browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            try:
                browser = p.chromium.launch(headless=True, args=browser_args)
                logging.info("Browser launched. Creating context...") # LOG AFTER launch
                context = browser.new_context(user_agent=user_agent)
                logging.info("Context created. Creating page...") # LOG AFTER context
                page = context.new_page()
                page.set_default_timeout(browser_timeout)
                logging.info("Page created.") # LOG AFTER page

            except PlaywrightError as launch_err:
                 logging.error(f"Playwright CRITICAL: Failed to launch browser instance: {launch_err}", exc_info=True)
                 raise RuntimeError(f"Failed to initialize browser environment") from launch_err
            except Exception as general_launch_err:
                logging.error(f"Unexpected error launching Playwright browser: {general_launch_err}", exc_info=True)
                raise RuntimeError(f"Unexpected error initializing browser environment") from general_launch_err

            # --- Navigate and Get Content ---
            try:
                logging.info(f"Navigating to {url} (Timeout: {browser_timeout/1000}s)...") # LOG BEFORE goto
                response = page.goto(url, wait_until='domcontentloaded', timeout=browser_timeout)
                status = response.status if response else 'N/A'
                logging.info(f"Navigation complete for {url}. Final Status: {status}") # LOG AFTER goto

                if response and not response.ok:
                     logging.error(f"HTTP Error after navigation to URL {url}: Status {response.status} {response.status_text}")
                     raise ConnectionError(f"Failed to fetch URL ({response.status} {response.status_text})")
                elif not response:
                     logging.warning(f"Playwright navigation to {url} did not yield a response object.")
                     raise ConnectionError("Navigation failed without receiving a server response")

                logging.info(f"Getting content from page for {url}...") # LOG BEFORE content
                html_content = page.content()
                logging.info(f"Content retrieved (length {len(html_content)}).") # LOG AFTER content

                if not html_content:
                     logging.warning(f"Rendered HTML content retrieved from {url} is empty.")
                     raise ValueError("Rendered HTML content is empty after successful navigation.")

            except PlaywrightTimeoutError as timeout_err:
                logging.error(f"Playwright CRITICAL: Timeout during navigation/wait for {url}", exc_info=True)
                raise TimeoutError(f"Timeout loading page or waiting for dynamic content") from timeout_err
            except PlaywrightError as nav_err:
                 logging.error(f"Playwright CRITICAL: Operational error for {url}: {nav_err}", exc_info=True)
                 err_str = str(nav_err).lower()
                 if any(e in err_str for e in ["net::err_", "dns_", "connection", "protocol error"]):
                      raise ConnectionError(f"Network or protocol error accessing URL ({nav_err})") from nav_err
                 elif any(e in err_str for e in ["ssl", "cert", "tls"]):
                      raise ConnectionError(f"SSL/TLS certificate issue accessing URL ({nav_err})") from nav_err
                 else:
                    raise RuntimeError(f"Browser automation error processing URL ({nav_err})") from nav_err
            except ConnectionError as ce:
                raise ce
            # --- End Navigation/Content Block ---

        # --- Extract with Trafilatura ---
        logging.info("Browser context closed. Starting Trafilatura extraction...") # LOG BEFORE trafilatura
        try:
            extracted_text = trafilatura.extract(html_content,
                                                 include_comments=False,
                                                 include_tables=True,
                                                 no_fallback=True)

            if not extracted_text or len(extracted_text.strip()) < 100:
                logging.warning(f"Initial Trafilatura extraction yielded little/no content from rendered HTML of {url}. Trying with fallback...")
                extracted_text = trafilatura.extract(html_content,
                                                     include_comments=False,
                                                     include_tables=True,
                                                     no_fallback=False)

                if not extracted_text or not extracted_text.strip():
                     raise ValueError("Content extraction failed - no main text found in rendered HTML even with fallback.")
                else:
                     logging.info(f"Extraction successful with fallback settings from rendered HTML for {url}")

            extracted_text = extracted_text.strip() if extracted_text else ""
            logging.info("Trafilatura extraction finished.") # LOG AFTER trafilatura success

        except Exception as traf_err:
            logging.error(f"Trafilatura CRITICAL: Extraction failed: {traf_err}", exc_info=True)
            raise ValueError(f"Failed to extract content from the webpage structure ({traf_err})")

        # --- Apply MAX_INPUT_CHARS truncation ---
        original_length = len(extracted_text)
        if original_length > MAX_INPUT_CHARS:
            extracted_text = extracted_text[:MAX_INPUT_CHARS]
            was_truncated = True
            logging.warning(f"Extracted text from URL '{url}' ({original_length:,} chars) truncated to {MAX_INPUT_CHARS:,} chars.")
        else:
            logging.info(f"Extracted text length ({original_length:,} chars) is within limit ({MAX_INPUT_CHARS:,}).")

        logging.info(f"Finished processing URL {url} successfully in fetch_and_extract.") # LOG SUCCESS END
        return extracted_text, was_truncated

    # --- Exception Handling: Map to standard exceptions ---
    except ConnectionError as e:
        logging.error(f"Caught ConnectionError processing URL {url}: {e}", exc_info=True)
        raise e
    except TimeoutError as e:
        logging.error(f"Caught TimeoutError processing URL {url}: {e}", exc_info=True)
        raise e
    except ValueError as e:
        logging.error(f"Caught ValueError processing URL {url}: {e}", exc_info=True)
        raise e
    except RuntimeError as e:
        logging.error(f"Caught RuntimeError processing URL {url}: {e}", exc_info=True)
        raise e
    except Exception as e:
        logging.error(f"Caught Unexpected Exception processing URL {url}: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected internal error occurred while processing the URL")
    # --- Resource Cleanup ---
    finally:
        if page and not page.is_closed():
            try:
                page.close()
                logging.debug(f"Playwright page closed for {url}")
            except Exception as close_err:
                logging.warning(f"Error closing Playwright page for {url}: {close_err}")
        if context:
            try:
                context.close()
                logging.debug(f"Playwright context closed for {url}")
            except Exception as close_err:
                logging.warning(f"Error closing Playwright context for {url}: {close_err}")
        if browser and browser.is_connected():
            try:
                browser.close()
                logging.debug(f"Playwright browser closed for {url}")
            except Exception as close_err:
                logging.warning(f"Error closing Playwright browser for {url}: {close_err}")