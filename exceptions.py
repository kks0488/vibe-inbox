"""Custom exceptions for Gmail Organizer."""


class GmailOrganizerError(Exception):
    """Base exception for Gmail Organizer."""
    pass


class ClassificationError(GmailOrganizerError):
    """Error during email classification."""
    pass


class GmailConnectionError(GmailOrganizerError):
    """Error connecting to Gmail API."""
    pass


class AuthenticationError(GmailOrganizerError):
    """Error during authentication."""
    pass


class RateLimitError(GmailOrganizerError):
    """API rate limit exceeded."""
    pass
