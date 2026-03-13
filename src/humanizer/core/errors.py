class HumanizerError(ValueError):
    """Base error for request-safe application failures."""


class ValidationError(HumanizerError):
    """Raised for invalid user input or unsupported configuration selections."""
