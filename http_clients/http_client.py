"""
http/client.py — HTTP client abstraction for bank adapters.

Provides a testable HTTP abstraction with multiple implementations:
- HttpClient: Abstract interface
- HttpResponse: Standard response container
- RequestsHttpClient: Production implementation with retry logic
- MockHttpClient: Test implementation with pattern matching
- FileHttpClient: Development implementation using fixture files

All implementations follow the same interface for easy dependency injection.
"""
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlparse

import requests


@dataclass
class HttpResponse:
    """
    Standard HTTP response container.
    
    Attributes:
        content: Response body as string
        status_code: HTTP status code (200, 404, etc.)
        url: The URL that was fetched
        error: Error message if fetch failed, None otherwise
    """
    content: str
    status_code: int
    url: str
    error: Optional[str] = None
    
    def is_success(self) -> bool:
        """Returns True if fetch succeeded (status 200-299, no error)."""
        return self.error is None and 200 <= self.status_code < 300


class HttpClient(ABC):
    """
    Abstract HTTP client interface.
    
    All implementations must provide a fetch() method that returns HttpResponse.
    Implementations should never raise exceptions - return HttpResponse with error instead.
    """
    
    @abstractmethod
    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        """
        Fetch content from URL.
        
        Args:
            url: URL to fetch
            ssl_verify: Whether to verify SSL certificates
            post_data: If provided, make POST request with this data
            headers: Optional HTTP headers to send
            
        Returns:
            HttpResponse with content or error
        """
        pass


class RequestsHttpClient(HttpClient):
    """
    Production HTTP client using requests library.
    
    Features:
    - Configurable connect and read timeouts (separate)
    - Configurable retries and retry delay
    - Exponential backoff on retry
    - Automatic User-Agent header
    - Never raises exceptions - returns error in HttpResponse
    - Smart retry logic (different handling for connect vs read timeouts)
    
    Example:
        client = RequestsHttpClient(
            connect_timeout=5.0,
            read_timeout=15.0, 
            max_retries=2
        )
        response = client.fetch("https://example.com/rates")
        if response.is_success():
            data = response.content
    """
    
    def __init__(
        self,
        connect_timeout: float = 5.0,   # Connection establishment timeout
        read_timeout: float = 15.0,      # Response reading timeout
        max_retries: int = 2,
        retry_delay: float = 2.0,
        user_agent: str = "EthiopianBankRateCollector/1.0"
    ):
        """
        Initialize RequestsHttpClient.
        
        Args:
            connect_timeout: Connection timeout in seconds (default: 5.0)
            read_timeout: Read timeout in seconds (default: 15.0)
            max_retries: Maximum number of retry attempts (default: 2)
            retry_delay: Base delay between retries in seconds (default: 2.0)
            user_agent: User-Agent header value
        """
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.timeout = (connect_timeout, read_timeout)  # requests format: (connect, read)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_agent = user_agent
    
    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        """
        Fetch content from URL with smart retry logic.
        
        Retries on timeout and connection errors with exponential backoff.
        Different handling for connect timeout vs read timeout.
        Never raises exceptions - returns error in HttpResponse.
        
        Args:
            url: URL to fetch
            ssl_verify: Whether to verify SSL certificates
            post_data: If provided, make POST request with this data
            headers: Optional HTTP headers to send
            
        Returns:
            HttpResponse with content or error
        """
        # Prepare headers
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)
        
        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if post_data:
                    response = requests.post(
                        url,
                        json=post_data,
                        headers=req_headers,
                        timeout=self.timeout,  # (connect_timeout, read_timeout)
                        verify=ssl_verify
                    )
                else:
                    response = requests.get(
                        url,
                        headers=req_headers,
                        timeout=self.timeout,  # (connect_timeout, read_timeout)
                        verify=ssl_verify
                    )
                
                # Success - return response
                return HttpResponse(
                    content=response.text,
                    status_code=response.status_code,
                    url=url,
                    error=None if response.ok else f"HTTP {response.status_code}"
                )
            
            except requests.ConnectTimeout as exc:
                # Connection timeout - likely network issue
                # Retry quickly with exponential backoff
                last_error = f"Connect timeout after {self.connect_timeout}s: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
            
            except requests.ReadTimeout as exc:
                # Read timeout - server is slow/stuck
                # Don't retry immediately (give server time to recover)
                last_error = f"Read timeout after {self.read_timeout}s: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * 3  # Longer delay for read timeouts
                    time.sleep(delay)
                    continue
            
            except requests.Timeout as exc:
                # Generic timeout (shouldn't happen with separate timeouts, but just in case)
                last_error = f"Timeout: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
            
            except requests.ConnectionError as exc:
                # Network/DNS issue - retry with exponential backoff
                last_error = f"Connection error: {exc}"
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
            
            except Exception as exc:
                # Other errors - don't retry
                last_error = f"Request failed: {exc}"
                break
        
        # All retries exhausted or non-retryable error
        return HttpResponse(
            content="",
            status_code=0,
            url=url,
            error=last_error
        )


class MockHttpClient(HttpClient):
    """
    Mock HTTP client for testing.
    
    Maps URL patterns to predefined responses.
    Tracks fetch count and last URL for test assertions.
    
    Example:
        client = MockHttpClient({
            "example.com": '{"rates": []}',
            "bank.et": '<html>rates</html>'
        })
        response = client.fetch("https://example.com/api")  # Matches "example.com"
        assert response.is_success()
        assert client.fetch_count == 1
    """
    
    def __init__(self, responses: Optional[Dict[str, str]] = None):
        """
        Initialize MockHttpClient.
        
        Args:
            responses: Dict mapping URL patterns to response content
                      Pattern matching is substring-based (e.g., "example.com" matches any URL containing it)
        """
        self.responses = responses or {}
        self.fetch_count = 0
        self.last_url = None
    
    def configure_response(self, pattern: str, content: str) -> None:
        """
        Add or update a response mapping.
        
        Args:
            pattern: URL pattern (substring or exact URL)
            content: Response content to return
        """
        self.responses[pattern] = content
    
    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        """
        Fetch content from configured responses.
        
        Matches URL against patterns (exact match first, then substring).
        Returns 404 if no pattern matches.
        
        Args:
            url: URL to fetch
            ssl_verify: Ignored (mock always succeeds)
            post_data: Ignored (mock always succeeds)
            headers: Ignored (mock always succeeds)
            
        Returns:
            HttpResponse with configured content or 404
        """
        self.fetch_count += 1
        self.last_url = url
        
        # Try exact match first
        if url in self.responses:
            return HttpResponse(
                content=self.responses[url],
                status_code=200,
                url=url,
                error=None
            )
        
        # Try substring match
        for pattern, content in self.responses.items():
            if pattern in url:
                return HttpResponse(
                    content=content,
                    status_code=200,
                    url=url,
                    error=None
                )
        
        # No match - return 404
        return HttpResponse(
            content="",
            status_code=404,
            url=url,
            error="Not Found (no pattern matched)"
        )


class FileHttpClient(HttpClient):
    """
    File-based HTTP client for development/testing.
    
    Loads responses from fixture files based on URL domain.
    Useful for testing with real bank data without network calls.
    
    Example:
        client = FileHttpClient(fixtures_dir="tests/fixtures")
        # Fetching "https://combanketh.et/api" loads "tests/fixtures/combanketh_et.json"
        response = client.fetch("https://combanketh.et/api")
    """
    
    def __init__(self, fixtures_dir: str = "tests/fixtures"):
        """
        Initialize FileHttpClient.
        
        Args:
            fixtures_dir: Directory containing fixture files
        """
        self.fixtures_dir = Path(fixtures_dir)
    
    def fetch(
        self,
        url: str,
        ssl_verify: bool = True,
        post_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> HttpResponse:
        """
        Fetch content from fixture file based on URL domain.
        
        Extracts domain from URL and maps to fixture filename:
        - "combanketh.et" → "combanketh_et.json" or "combanketh_et.html"
        
        Tries both .json and .html extensions.
        Returns 404 if fixture not found.
        
        Args:
            url: URL to fetch
            ssl_verify: Ignored (file always succeeds)
            post_data: Ignored (file always succeeds)
            headers: Ignored (file always succeeds)
            
        Returns:
            HttpResponse with fixture content or 404
        """
        # Extract domain from URL and convert to filename
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Replace dots with underscores for filename
        base_name = domain.replace('.', '_')
        
        # Try .json first, then .html
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
        
        # Fixture not found
        return HttpResponse(
            content="",
            status_code=404,
            url=url,
            error=f"Fixture not found: {base_name}.json or {base_name}.html"
        )
