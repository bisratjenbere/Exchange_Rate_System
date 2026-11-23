class StaleObservationError(Exception):
    """Raised when the locked row's version differs from what the caller read."""
