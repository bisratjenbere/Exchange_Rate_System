"""
Browser instance pooling for Playwright automation.

Eliminates 2-3s startup overhead per browser-based source by reusing
browser instances across multiple collections.

Usage:
    pool = get_browser_pool()
    browser = pool.acquire()
    try:
        # Use browser
        page = browser.new_page()
        ...
    finally:
        pool.release(browser)
"""

from queue import Queue, Empty
from threading import Lock
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class BrowserPool:
    _instance: Optional["BrowserPool"] = None

    """
    Manages a pool of reusable Playwright browser instances.
    
    Features:
    - Lazy initialization (only creates browsers when needed)
    - Automatic recycling (after N uses to prevent memory leaks)
    - Thread-safe acquire/release
    - Graceful degradation (creates temp browser if pool exhausted)
    
    Configuration:
    - max_browsers: Maximum concurrent browsers (default: 3)
    - recycle_after_uses: Recycle browser after N uses (default: 10)
    """
    
    def __init__(self, max_browsers: int = 3, recycle_after_uses: int = 10):
        self.max_browsers = max_browsers
        self.recycle_after_uses = recycle_after_uses
        
        self.pool = Queue(maxsize=max_browsers)
        self.usage_count = {}
        self.lock = Lock()
        self.playwright = None
        self.initialized = False
        
        # Metrics
        self.total_acquisitions = 0
        self.pool_hits = 0
        self.pool_misses = 0
        self.browsers_recycled = 0
    
    def initialize(self):
        """
        Lazy initialization on first use.
        Thread-safe double-checked locking.
        """
        if self.initialized:
            return
        
        with self.lock:
            if self.initialized:
                return
            
            logger.info(f"Initializing browser pool with {self.max_browsers} browsers")
            
            try:
                from playwright.sync_api import sync_playwright
                self.playwright = sync_playwright().start()
                
                for i in range(self.max_browsers):
                    browser = self._create_browser()
                    self.pool.put(browser)
                    self.usage_count[id(browser)] = 0
                    logger.debug(f"Browser {i+1}/{self.max_browsers} initialized")
                
                self.initialized = True
                logger.info("Browser pool initialization complete")
            except ImportError:
                logger.warning("Playwright not available, browser pool disabled")
                self.initialized = False
            except Exception as e:
                logger.error(f"Failed to initialize browser pool: {e}", exc_info=True)
                self.initialized = False
    
    def _create_browser(self):
        """
        Create a new browser instance with optimized settings.
        
        Optimizations:
        - Headless mode (no GUI overhead)
        - Disabled dev-shm (prevents crashes in containers)
        - No sandbox (GitHub Actions compatibility)
        - Disabled automation detection
        """
        return self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-dev-shm-usage',          # Prevent /dev/shm exhaustion
                '--no-sandbox',                      # Required for containers
                '--disable-setuid-sandbox',
                '--disable-web-security',            # Allow cross-origin requests
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-blink-features=AutomationControlled',  # Anti-detection
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-extensions',
                '--disable-features=TranslateUI',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-renderer-backgrounding',
                '--disable-sync',
                '--metrics-recording-only',
                '--no-pings',
            ]
        )
    
    def acquire(self, timeout: float = 30.0):
        """
        Acquire a browser from the pool.
        
        Args:
            timeout: Maximum time to wait for available browser (seconds)
        
        Returns:
            Browser instance
        
        Behavior:
        - If pool has available browser, returns it immediately
        - If browser needs recycling, closes and creates new one
        - If pool exhausted, creates temporary browser (pool miss)
        """
        self.initialize()
        
        if not self.initialized:
            # Playwright not available, return None
            logger.warning("Browser pool not initialized, returning None")
            return None
        
        self.total_acquisitions += 1
        
        try:
            browser = self.pool.get(timeout=timeout)
            self.pool_hits += 1
            
            # Check if needs recycling
            browser_id = id(browser)
            uses = self.usage_count.get(browser_id, 0)
            
            if uses >= self.recycle_after_uses:
                logger.info(f"Recycling browser after {uses} uses")
                try:
                    browser.close()
                except Exception as e:
                    logger.warning(f"Error closing browser during recycle: {e}")
                
                browser = self._create_browser()
                self.usage_count[id(browser)] = 0
                self.browsers_recycled += 1
            
            logger.debug(f"Browser acquired (uses: {uses})")
            return browser
            
        except Empty:
            logger.warning(
                f"Browser pool exhausted after {timeout}s, creating temporary browser"
            )
            self.pool_misses += 1
            return self._create_browser()
    
    def release(self, browser):
        """
        Return browser to pool.
        
        Args:
            browser: Browser instance to return
        
        Behavior:
        - Increments usage counter
        - Attempts to put back in pool
        - If pool full, closes excess browser
        """
        if not browser:
            return
        
        browser_id = id(browser)
        self.usage_count[browser_id] = self.usage_count.get(browser_id, 0) + 1
        
        try:
            self.pool.put_nowait(browser)
            logger.debug("Browser released to pool")
        except Exception:
            # Pool full (can happen with temporary browsers)
            logger.debug("Pool full, closing excess browser")
            try:
                browser.close()
            except Exception as e:
                logger.warning(f"Error closing excess browser: {e}")
    
    def shutdown(self):
        """
        Cleanup all browsers and playwright.
        
        Should be called on application shutdown.
        """
        if not self.initialized:
            return
        
        logger.info("Shutting down browser pool")
        
        closed_count = 0
        while not self.pool.empty():
            try:
                browser = self.pool.get_nowait()
                browser.close()
                closed_count += 1
            except Empty:
                break
            except Exception as e:
                logger.warning(f"Error closing browser during shutdown: {e}")
        
        logger.info(f"Closed {closed_count} browsers")
        
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
        
        self.initialized = False
        logger.info("Browser pool shutdown complete")
    
    def get_metrics(self) -> dict:
        """
        Return pool performance metrics.
        
        Useful for monitoring and optimization.
        """
        hit_rate = (
            self.pool_hits / self.total_acquisitions * 100
            if self.total_acquisitions > 0
            else 0.0
        )
        
        return {
            'total_acquisitions': self.total_acquisitions,
            'pool_hits': self.pool_hits,
            'pool_misses': self.pool_misses,
            'hit_rate_percent': round(hit_rate, 2),
            'browsers_recycled': self.browsers_recycled,
            'pool_size': self.max_browsers,
            'recycle_threshold': self.recycle_after_uses,
            'initialized': self.initialized,
        }
    
    def __enter__(self):
        """Context manager support"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.shutdown()


# Singleton managed at class level to avoid module-level mutable globals
_pool_lock = Lock()


def get_browser_pool() -> BrowserPool:
    if BrowserPool._instance is None:
        with _pool_lock:
            if BrowserPool._instance is None:
                BrowserPool._instance = BrowserPool(
                    max_browsers=3,
                    recycle_after_uses=10,
                )
    return BrowserPool._instance


def shutdown_browser_pool():
    with _pool_lock:
        if BrowserPool._instance is not None:
            BrowserPool._instance.shutdown()
            BrowserPool._instance = None
