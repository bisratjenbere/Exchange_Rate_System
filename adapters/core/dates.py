"""
Date parsing and timezone handling.

All business dates use Africa/Addis_Ababa timezone.
"""

from datetime import date, datetime
from typing import Optional
import pytz


# Ethiopian timezone
ADDIS_ABABA_TZ = pytz.timezone("Africa/Addis_Ababa")


def business_date_now() -> date:
    """
    Get current business date in Addis Ababa timezone.
    
    Returns:
        date: Today's date in Africa/Addis_Ababa
    
    Example:
        # If UTC is 2024-01-15 23:00 (11pm), Addis is 2024-01-16 02:00 (2am)
        business_date_now() → date(2024, 1, 16)
    """
    now_utc = datetime.now(pytz.UTC)
    now_addis = now_utc.astimezone(ADDIS_ABABA_TZ)
    return now_addis.date()


def parse_iso_date(text: str) -> Optional[date]:
    """
    Parse ISO 8601 date string (YYYY-MM-DD).
    
    Args:
        text: Date string (e.g., "2024-01-15")
    
    Returns:
        date: Parsed date
        None: If parsing fails
    
    Examples:
        parse_iso_date("2024-01-15") → date(2024, 1, 15)
        parse_iso_date("2024-1-5") → date(2024, 1, 5)
        parse_iso_date("invalid") → None
    """
    if not text:
        return None
    
    try:
        return datetime.fromisoformat(text).date()
    except (ValueError, AttributeError):
        return None


def parse_local_datetime(text: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """
    Parse datetime string in local format, return as UTC datetime.
    
    Args:
        text: Datetime string
        fmt: strptime format string
    
    Returns:
        datetime: Parsed datetime in UTC
        None: If parsing fails
    
    Examples:
        parse_local_datetime("2024-01-15 14:30:00")
        → datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC)  # Addis is UTC+3
    """
    if not text:
        return None
    
    try:
        # Parse as naive datetime
        dt_naive = datetime.strptime(text, fmt)
        
        # Localize to Addis Ababa timezone
        dt_local = ADDIS_ABABA_TZ.localize(dt_naive)
        
        # Convert to UTC
        return dt_local.astimezone(pytz.UTC)
    
    except (ValueError, AttributeError):
        return None


def days_ago(d: date, reference: date = None) -> int:
    """
    Calculate days between date and reference (default: today).
    
    Args:
        d: Date to check
        reference: Reference date (default: business_date_now())
    
    Returns:
        int: Days difference (positive = d is in past)
    
    Examples:
        # If today is 2024-01-15
        days_ago(date(2024, 1, 10)) → 5
        days_ago(date(2024, 1, 20)) → -5 (future)
    """
    if reference is None:
        reference = business_date_now()
    
    return (reference - d).days
