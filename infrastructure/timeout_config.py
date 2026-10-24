"""
infrastructure/timeout_config.py — Bank-specific timeout configuration.

Provides adaptive timeout configuration based on observed bank behavior.
Different banks have different response time characteristics, so we use
bank-specific timeouts to reduce false failures while maintaining efficiency.
"""

# Bank-specific timeout configurations
# Format: {adapter_key: {timeout: seconds, max_retries: count, connect_timeout: seconds}}
BANK_TIMEOUT_CONFIG = {
    # === SLOW BANKS (Consistently slow response times) ===
    # These banks typically respond in 10-30 seconds
    "cbe_html": {
        "connect_timeout": 5.0,
        "read_timeout": 30.0,
        "max_retries": 1,
        "reason": "Large government bank, slow server during business hours"
    },
    "dashen_html": {
        "connect_timeout": 5.0,
        "read_timeout": 25.0,
        "max_retries": 1,
        "reason": "Slow HTML parsing, large page size"
    },
    "goh_betoch_html": {
        "connect_timeout": 5.0,
        "read_timeout": 30.0,
        "max_retries": 1,
        "reason": "Intermittent timeout issues, slow response"
    },
    "boa_html": {
        "connect_timeout": 5.0,
        "read_timeout": 25.0,
        "max_retries": 1,
        "reason": "SSL verification disabled, occasionally slow"
    },
    
    # === MEDIUM SPEED BANKS ===
    # These banks typically respond in 5-15 seconds
    "wegagen_api": {
        "connect_timeout": 5.0,
        "read_timeout": 15.0,
        "max_retries": 2,
        "reason": "Strapi API, generally reliable but can be slow"
    },
    "awash_api": {
        "connect_timeout": 5.0,
        "read_timeout": 15.0,
        "max_retries": 2,
        "reason": "JSON API, moderate speed"
    },
    "abay_html": {
        "connect_timeout": 5.0,
        "read_timeout": 18.0,
        "max_retries": 2,
        "reason": "HTML table parsing, moderate complexity"
    },
    
    # === FAST BANKS (Quick response) ===
    # These banks typically respond in <5 seconds
    "rammis_api": {
        "connect_timeout": 3.0,
        "read_timeout": 10.0,
        "max_retries": 3,
        "reason": "Fast JSON API, very reliable"
    },
    "zemen_api": {
        "connect_timeout": 3.0,
        "read_timeout": 10.0,
        "max_retries": 3,
        "reason": "Fast JSON API"
    },
    
    # === SPECIAL CASES ===
    "anbesa_browser": {
        "connect_timeout": 10.0,
        "read_timeout": 60.0,
        "max_retries": 0,
        "reason": "Browser automation with Playwright, needs longer timeout for JS rendering"
    },
    "ahadu_text": {
        "connect_timeout": 5.0,
        "read_timeout": 20.0,
        "max_retries": 2,
        "reason": "Text extraction, moderate complexity"
    },
    "shabelle_html": {
        "connect_timeout": 5.0,
        "read_timeout": 20.0,
        "max_retries": 2,
        "reason": "Custom div structure, moderate parsing time"
    },
    
    # === DEFAULT FOR UNKNOWN BANKS ===
    "default": {
        "connect_timeout": 5.0,
        "read_timeout": 15.0,
        "max_retries": 2,
        "reason": "Conservative default for new/unknown banks"
    }
}


def get_timeout_config(adapter_key: str) -> dict:
    """
    Get timeout configuration for a specific adapter.
    
    Returns bank-specific config if available, otherwise returns default.
    
    Args:
        adapter_key: The adapter key (e.g., "cbe_html", "wegagen_api")
    
    Returns:
        Dict with keys: connect_timeout, read_timeout, max_retries, reason
    
    Example:
        config = get_timeout_config("cbe_html")
        client = RequestsHttpClient(
            connect_timeout=config["connect_timeout"],
            read_timeout=config["read_timeout"],
            max_retries=config["max_retries"]
        )
    """
    return BANK_TIMEOUT_CONFIG.get(adapter_key, BANK_TIMEOUT_CONFIG["default"])


def get_all_slow_banks() -> list:
    """
    Get list of banks configured with slow timeouts (>20s read timeout).
    
    Useful for monitoring and alerts.
    
    Returns:
        List of (adapter_key, config) tuples for slow banks
    """
    slow_banks = []
    for adapter_key, config in BANK_TIMEOUT_CONFIG.items():
        if adapter_key == "default":
            continue
        if config.get("read_timeout", 0) > 20.0:
            slow_banks.append((adapter_key, config))
    return slow_banks


def get_summary() -> str:
    """
    Get human-readable summary of timeout configurations.
    
    Returns:
        Formatted string showing timeout config summary
    """
    lines = [
        "=== TIMEOUT CONFIGURATION SUMMARY ===",
        ""
    ]
    
    # Group by speed
    slow = []
    medium = []
    fast = []
    
    for adapter_key, config in BANK_TIMEOUT_CONFIG.items():
        if adapter_key == "default":
            continue
        
        read_timeout = config.get("read_timeout", 15.0)
        if read_timeout >= 25.0:
            slow.append((adapter_key, config))
        elif read_timeout >= 15.0:
            medium.append((adapter_key, config))
        else:
            fast.append((adapter_key, config))
    
    if slow:
        lines.append(f"SLOW BANKS ({len(slow)} banks, timeout ≥25s):")
        for adapter_key, config in slow:
            lines.append(f"  • {adapter_key}: {config['read_timeout']}s read, {config['max_retries']} retries")
        lines.append("")
    
    if medium:
        lines.append(f"MEDIUM BANKS ({len(medium)} banks, timeout 15-24s):")
        for adapter_key, config in medium:
            lines.append(f"  • {adapter_key}: {config['read_timeout']}s read, {config['max_retries']} retries")
        lines.append("")
    
    if fast:
        lines.append(f"FAST BANKS ({len(fast)} banks, timeout <15s):")
        for adapter_key, config in fast:
            lines.append(f"  • {adapter_key}: {config['read_timeout']}s read, {config['max_retries']} retries")
        lines.append("")
    
    default_config = BANK_TIMEOUT_CONFIG["default"]
    lines.append(f"DEFAULT: {default_config['read_timeout']}s read, {default_config['max_retries']} retries")
    
    return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    print(get_summary())
    print("\n" + "=" * 60)
    print("\nExample: Getting config for CBE")
    config = get_timeout_config("cbe_html")
    print(f"  Connect timeout: {config['connect_timeout']}s")
    print(f"  Read timeout: {config['read_timeout']}s")
    print(f"  Max retries: {config['max_retries']}")
    print(f"  Reason: {config['reason']}")
