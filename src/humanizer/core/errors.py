class HumanizerError(ValueError):
    """Base error for request-safe application failures."""


class ValidationError(HumanizerError):
    """Raised for invalid user input or unsupported configuration selections."""


class ProviderTransientError(HumanizerError):
    """Raised when a provider is temporarily unavailable for the current request."""
