"""
Configuration management for the Exchange Rate System.

This module provides centralized configuration loading from environment
variables with sensible defaults, following 12-factor app principles.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """
    Centralized configuration loaded from environment variables.
    
    This class provides a single source of truth for all configuration
    settings, replacing hardcoded module-level constants throughout
    the codebase.
    
    Environment Variables:
        REQUEST_TIMEOUT: HTTP request timeout in seconds (default: 15)
        RATE_LIMIT_DELAY: Delay between requests in seconds (default: 2.0)
        MAX_RETRIES: Maximum HTTP retry attempts (default: 2)
        DATABASE_URL: PostgreSQL connection string (required in production)
    
    All values have sensible defaults for development except DATABASE_URL
    which must be set in production environments.
    
    Example:
        >>> # Use defaults
        >>> config = Config()
        >>> config.REQUEST_TIMEOUT
        15
        
        >>> # Override via environment
        >>> os.environ['REQUEST_TIMEOUT'] = '30'
        >>> config = Config()
        >>> config.REQUEST_TIMEOUT
        30
        
        >>> # Inject into components
        >>> scheduler = Scheduler(config=config)
    """
    
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    """User agent string for HTTP requests to bank websites."""
    
    REQUEST_TIMEOUT: int = field(
        default_factory=lambda: int(os.getenv('REQUEST_TIMEOUT', '15'))
    )
    """HTTP request timeout in seconds. Override with REQUEST_TIMEOUT env var."""
    
    RATE_LIMIT_DELAY: float = field(
        default_factory=lambda: float(os.getenv('RATE_LIMIT_DELAY', '2.0'))
    )
    """Delay between HTTP requests in seconds. Override with RATE_LIMIT_DELAY env var."""
    
    MAX_RETRIES: int = field(
        default_factory=lambda: int(os.getenv('MAX_RETRIES', '2'))
    )
    """Maximum number of HTTP retry attempts. Override with MAX_RETRIES env var."""
    
    DATABASE_URL: str = field(
        default_factory=lambda: os.getenv('DATABASE_URL', '')
    )
    """PostgreSQL connection string. Must be set in production via DATABASE_URL env var."""
    
    def __post_init__(self):
        """
        Validate configuration values after initialization.
        
        Raises:
            ValueError: If any configuration value is invalid
        """
        if self.REQUEST_TIMEOUT <= 0:
            raise ValueError(
                f"REQUEST_TIMEOUT must be > 0, got {self.REQUEST_TIMEOUT}"
            )
        
        if self.RATE_LIMIT_DELAY < 0:
            raise ValueError(
                f"RATE_LIMIT_DELAY must be >= 0, got {self.RATE_LIMIT_DELAY}"
            )
        
        if self.MAX_RETRIES < 0:
            raise ValueError(
                f"MAX_RETRIES must be >= 0, got {self.MAX_RETRIES}"
            )
