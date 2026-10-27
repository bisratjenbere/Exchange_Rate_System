import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlparse

import requests

try:
    from http_clients.cloudflare_bypass import CloudflareBypass
    CLOUDFLARE_BYPASS_AVAILABLE = True
except ImportError:
    CLOUDFLARE_BYPASS_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class HttpResponse:
    content: str
    status_code: int
    url: str
    error: Optional[str] = None

    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300

class HttpClient(ABC):

    @abstractmethod
    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        pass

class RequestsHttpClient(HttpClient):

    def __init__(
        self,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        max_retries: int = 2,
        retry_delay: float = 2.0,
        user_agent: str = "EthiopianBankRateCollector/1.0",
        use_cloudflare_bypass: bool = False
    ):
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.timeout = (connect_timeout, read_timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_agent = user_agent
        self.use_cloudflare_bypass = use_cloudflare_bypass

        self.cloudflare_bypass = None
        if use_cloudflare_bypass and CLOUDFLARE_BYPASS_AVAILABLE:
            self.cloudflare_bypass = CloudflareBypass()
            logger.info("Cloudflare bypass enabled for this client")

    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)

        if self.cloudflare_bypass and not post_data:
            try:
                logger.debug(f"Attempting Cloudflare bypass for {url}")
                content = self.cloudflare_bypass.get(url, timeout=int(self.read_timeout))
                return HttpResponse(
                    content=content,
                    status_code=200,
                    url=url,
                    error=None
                )
            except Exception as e:
                logger.warning(f"Cloudflare bypass failed: {e}. Falling back to regular request")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if post_data:
                    response = requests.post(
                        url,
                        json=post_data,
                        headers=req_headers,
                        timeout=self.timeout,
                        verify=ssl_verify
                    )
                else:
                    response = requests.get(
                        url,
                        headers=req_headers,
                        timeout=self.timeout,
                        verify=ssl_verify
                    )

                if self._is_cloudflare_challenge(response.text) and not post_data:
                    if self.cloudflare_bypass:
                        try:
                            logger.info("Cloudflare challenge detected, forcing bypass with Playwright")
                            content = self.cloudflare_bypass.get(url, timeout=int(self.read_timeout), force_playwright=True)
                            return HttpResponse(
                                content=content,
                                status_code=200,
                                url=url,
                                error=None
                            )
                        except Exception as e:
                            logger.error(f"Cloudflare bypass with Playwright failed: {e}")

                    return HttpResponse(
                        content=response.text,
                        status_code=response.status_code,
                        url=url,
                        error="Cloudflare protection detected. Install cloudscraper or playwright to bypass."
                    )

                return HttpResponse(
                    content=response.text,
                    status_code=response.status_code,
                    url=url,
                    error=None if response.ok else f"HTTP {response.status_code}"
                )

            except requests.ConnectTimeout as exc:
                last_error = f"Connect timeout after {self.connect_timeout}s: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue

            except requests.ReadTimeout as exc:
                last_error = f"Read timeout after {self.read_timeout}s: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * 3
                    time.sleep(delay)
                    continue

            except requests.Timeout as exc:
                last_error = f"Timeout: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue

            except requests.ConnectionError as exc:
                last_error = f"Connection error: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue

            except Exception as exc:
                last_error = f"Request failed: {exc}"
                break

        return HttpResponse(
            content="",
            status_code=0,
            url=url,
            error=last_error
        )

    def _is_cloudflare_challenge(self, html: str) -> bool:
        indicators = [
            'One moment, please...',
            'Checking your browser',
            'Please wait while we check your browser',
            'ray id',
            'cf-browser-verification',
        ]

        html_lower = html.lower()
        return any(indicator.lower() in html_lower for indicator in indicators)

class MockHttpClient(HttpClient):

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self.responses = responses or {}
        self.fetch_count = 0
        self.last_url = None

    def configure_response(self, pattern: str, content: str) -> None:
        self.responses[pattern] = content

    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        self.fetch_count += 1
        self.last_url = url

        if url in self.responses:
            return HttpResponse(
                content=self.responses[url],
                status_code=200,
                url=url,
                error=None
            )

        for pattern, content in self.responses.items():
            if pattern in url:
                return HttpResponse(
                    content=content,
                    status_code=200,
                    url=url,
                    error=None
                )

        return HttpResponse(
            content="",
            status_code=404,
            url=url,
            error="Not Found (no pattern matched)"
        )

class FileHttpClient(HttpClient):

    def __init__(self, fixtures_dir: str = "tests/fixtures"):
        self.fixtures_dir = Path(fixtures_dir)

    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        base_name = domain.replace('.', '_')

        for ext in ['.json', '.html']:
            fixture_path = self.fixtures_dir / f"{base_name}{ext}"
            if fixture_path.exists():
                try:
                    content = fixture_path.read_text(encoding='utf-8')
                    return HttpResponse(
                        content=content,
                        status_code=200,
                        url=url,
                        error=None
                    )
                except Exception as exc:
                    return HttpResponse(
                        content="",
                        status_code=500,
                        url=url,
                        error=f"Failed to read fixture: {exc}"
                    )

        return HttpResponse(
            content="",
            status_code=404,
            url=url,
            error=f"Fixture not found: {base_name}.json or {base_name}.html"
        )
