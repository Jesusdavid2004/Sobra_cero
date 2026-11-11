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


class AIResponseInvalidError(Exception):
    """Raised when an AI provider cannot produce output matching the requested schema."""


class AIProviderUnavailableError(Exception):
    """Raised when an AI provider or its request-policy store is unavailable."""


class AIQuotaExceededError(Exception):
    """Raised when a user exceeds the daily AI request allowance."""


class InvalidImageError(ValueError):
    """Raised when an uploaded image is corrupt or outside supported image limits."""


class RescuePermissionError(Exception):
    """Raised when the actor's role cannot use rescue plans."""


class RescueLotNotFoundError(Exception):
    """Raised when a lot does not exist or is not visible to the actor."""


class RescuePlanNotFoundError(Exception):
    """Raised when a rescue plan does not exist or is not visible to the actor."""


class LotNotRescuableError(Exception):
    """Raised when a lot is inactive, empty, or past its operating deadline."""


class RescuePlanStaleError(Exception):
    """Raised when the lot changed after a rescue plan was generated."""


class InvalidRescuePlanTransitionError(Exception):
    """Raised when a rescue plan decision conflicts with its current status."""


class RescuePlanConflictError(Exception):
    """Raised when a concurrent request already created a pending rescue plan."""


class ShopNotFoundError(Exception):
    """Raised when a public shop profile does not exist."""


class SimulationUnavailableError(Exception):
    """Raised when a plan has no numbers to simulate from."""


class SimulationInvalidError(ValueError):
    """Raised when scenario parameters are outside what the lot allows."""


class AnalysisUnavailableError(Exception):
    """Raised when the analysis service is unreachable or exceeds its deadline."""


class AnalysisFailedError(Exception):
    """Raised when the analysis service rejects a request or its credentials."""


class InvalidAnalysisRequestError(ValueError):
    """Raised when an analysis request violates the semantic limits of the contract."""


class DiscoveryInvalidError(Exception):
    """The discovery search parameters are not a valid request."""
