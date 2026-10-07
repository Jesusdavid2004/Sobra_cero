class InsufficientSalesHistoryError(Exception):
    """Raised when a product does not have enough daily sales to forecast waste."""


class BatchAlreadyReservedError(Exception):
    """Raised when a customer attempts to reserve the same batch more than once."""


class RiskScoreValidationError(ValueError):
    """Raised when a waste-risk score is outside the 0-100 range."""
