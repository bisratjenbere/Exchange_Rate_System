import pytest
from unittest.mock import Mock, patch, MagicMock
from scheduler.browser_pool import BrowserPool, get_browser_pool, shutdown_browser_pool


class TestBrowserPool:
    
    def test_lazy_initialization(self):
        """Pool should not initialize until first acquire"""
        pool = BrowserPool(max_browsers=2)
        assert not pool.initialized
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            mock_playwright.chromium.launch.return_value = Mock()
            
            browser = pool.acquire()
            assert pool.initialized
            assert mock_playwright.chromium.launch.call_count == 2
    
    def test_acquire_release_cycle(self):
        """Browser should be reusable after release"""
        pool = BrowserPool(max_browsers=1)
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            mock_browser = Mock()
            mock_playwright.chromium.launch.return_value = mock_browser
            
            # First acquire
            browser1 = pool.acquire()
            assert browser1 == mock_browser
            
            # Release
            pool.release(browser1)
            
            # Second acquire should reuse same browser
            browser2 = pool.acquire()
            assert browser2 == mock_browser
            assert mock_playwright.chromium.launch.call_count == 1  # Only created once
    
    def test_browser_recycling(self):
        """Browser should be recycled after N uses"""
        pool = BrowserPool(max_browsers=1, recycle_after_uses=3)
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            
            mock_browsers = [Mock() for _ in range(2)]
            mock_playwright.chromium.launch.side_effect = mock_browsers
            
            # Use browser 3 times
            for i in range(3):
                browser = pool.acquire()
                pool.release(browser)
            
            # 4th acquisition should trigger recycle
            browser = pool.acquire()
            mock_browsers[0].close.assert_called_once()
            assert mock_playwright.chromium.launch.call_count == 2
    
    def test_pool_exhaustion(self):
        """Should create temporary browser when pool exhausted"""
        pool = BrowserPool(max_browsers=1)
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            mock_playwright.chromium.launch.return_value = Mock()
            
            # Acquire both browsers (pool + temp)
            browser1 = pool.acquire()
            browser2 = pool.acquire(timeout=0.1)  # Should create temp
            
            assert pool.pool_hits == 1
            assert pool.pool_misses == 1
            assert mock_playwright.chromium.launch.call_count == 2
    
    def test_metrics(self):
        """Metrics should track acquisitions accurately"""
        pool = BrowserPool(max_browsers=1)
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            mock_playwright.chromium.launch.return_value = Mock()
            
            browser = pool.acquire()
            pool.release(browser)
            browser = pool.acquire()
            
            metrics = pool.get_metrics()
            assert metrics['total_acquisitions'] == 2
            assert metrics['pool_hits'] == 2
            assert metrics['pool_misses'] == 0
            assert metrics['hit_rate_percent'] == 100.0
    
    def test_shutdown(self):
        """Shutdown should close all browsers"""
        pool = BrowserPool(max_browsers=2)
        
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            
            mock_browsers = [Mock() for _ in range(2)]
            mock_playwright.chromium.launch.side_effect = mock_browsers
            
            pool.initialize()
            pool.shutdown()
            
            for browser in mock_browsers:
                browser.close.assert_called_once()
            
            mock_playwright.stop.assert_called_once()
            assert not pool.initialized
    
    def test_playwright_not_available(self):
        """Should handle case when playwright is not installed"""
        pool = BrowserPool(max_browsers=1)
        
        # Mock the import to raise ImportError
        import sys
        with patch.dict(sys.modules, {'playwright.sync_api': None}):
            browser = pool.acquire()
            assert browser is None
            assert not pool.initialized
    
    def test_context_manager(self):
        """Should support context manager protocol"""
        with patch('playwright.sync_api.sync_playwright') as mock_pw:
            mock_playwright = MagicMock()
            mock_pw.return_value.start.return_value = mock_playwright
            mock_playwright.chromium.launch.return_value = Mock()
            
            with BrowserPool(max_browsers=1) as pool:
                assert pool.initialized
            
            # Should be shutdown after exiting context
            assert not pool.initialized


class TestBrowserPoolSingleton:
    
    def test_singleton_returns_same_instance(self):
        """get_browser_pool should return same instance"""
        shutdown_browser_pool()  # Clean slate
        
        pool1 = get_browser_pool()
        pool2 = get_browser_pool()
        
        assert pool1 is pool2
    
    def test_shutdown_clears_singleton(self):
        """shutdown_browser_pool should allow new instance"""
        pool1 = get_browser_pool()
        shutdown_browser_pool()
        pool2 = get_browser_pool()
        
        assert pool1 is not pool2
