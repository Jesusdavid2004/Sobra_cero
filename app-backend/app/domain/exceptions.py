class InsufficientSalesHistoryError(Exception):
    """Raised when a product does not have enough daily sales to forecast waste."""


class InsufficientSalesTrainingDataError(Exception):
    """Raised when sales history cannot support a time-based model evaluation."""


class InvalidSalesHistoryCsvError(ValueError):
    """Raised when a sales-history CSV does not match the supported import format."""


class BatchAlreadyReservedError(Exception):
    """Raised when a customer attempts to reserve the same batch more than once."""


class RiskScoreValidationError(ValueError):
    """Raised when a waste-risk score is outside the 0-100 range."""


class DiscountPercentValidationError(ValueError):
    """Raised when a discount is outside the allowed domain range."""


class InvalidMoneyError(ValueError):
    """Raised when a money value has an invalid amount or currency."""


class InvalidBatchQuantityError(ValueError):
    """Raised when batch or reservation quantity is not positive."""


class BatchNotReservableError(Exception):
    """Raised when a batch is not in a state that permits reservation."""


class InsufficientStockError(Exception):
    """Raised when a batch does not have enough stock for an operation."""


class BatchExpiredError(Exception):
    """Raised when an operation targets a batch whose expiry has passed."""


class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an email that already exists."""


class InvalidCredentialsError(Exception):
    """Raised when an email or password does not identify a valid user."""


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is invalid, expired, or already rotated."""


class RefreshSessionStoreUnavailableError(Exception):
    """Raised when the session store cannot safely rotate or revoke a token."""
