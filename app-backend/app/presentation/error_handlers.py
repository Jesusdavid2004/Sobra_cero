"""Centralized mapping from domain exceptions to the { code, message_key } error contract."""

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.domain.exceptions import (
    AnalysisFailedError,
    DiscoveryInvalidError,
    DonationLotNotFoundError,
    DonationOfferConflictError,
    DonationOfferNotFoundError,
    DonationOfferStateError,
    DonationPermissionError,
    DonationQuantityInvalidError,
    DonationReceiverIncompatibleError,
    DonationStockUnavailableError,
    InvalidRescuePlanTransitionError,
    LotNotRescuableError,
    PlaceInvalidError,
    ReceiverAlreadyExistsError,
    ReceiverInvalidError,
    ReceiverNotFoundError,
    RescueLotNotFoundError,
    RescuePermissionError,
    RescuePlanConflictError,
    RescuePlanNotFoundError,
    RescuePlanStaleError,
    ScannerBusinessNotFoundError,
    ScannerPermissionError,
    ScannerSourceNotFoundError,
    ShopNotFoundError,
    SimulationInvalidError,
    SimulationUnavailableError,
    SourceInvalidError,
    SourceNotRunnableError,
    SourceUrlRejectedError,
)

ERROR_CONTRACT: dict[type[Exception], tuple[int, str]] = {
    RescuePermissionError: (403, "rescue_permission_denied"),
    RescueLotNotFoundError: (404, "rescue_lot_not_found"),
    RescuePlanNotFoundError: (404, "rescue_plan_not_found"),
    LotNotRescuableError: (409, "rescue_lot_not_rescuable"),
    RescuePlanStaleError: (409, "rescue_plan_stale"),
    InvalidRescuePlanTransitionError: (409, "rescue_plan_invalid_transition"),
    RescuePlanConflictError: (409, "rescue_plan_conflict"),
    AnalysisFailedError: (502, "analysis_failed"),
    ShopNotFoundError: (404, "shop_not_found"),
    SimulationUnavailableError: (409, "simulation_unavailable"),
    SimulationInvalidError: (422, "simulation_invalid"),
    DiscoveryInvalidError: (422, "discovery_invalid"),
    PlaceInvalidError: (422, "place_invalid"),
    ScannerPermissionError: (403, "scanner_permission_denied"),
    ScannerSourceNotFoundError: (404, "scanner_source_not_found"),
    ScannerBusinessNotFoundError: (404, "scanner_business_not_found"),
    SourceInvalidError: (422, "scanner_source_invalid"),
    SourceUrlRejectedError: (422, "scanner_url_rejected"),
    SourceNotRunnableError: (409, "scanner_source_not_runnable"),
    DonationPermissionError: (403, "donation_permission_denied"),
    DonationLotNotFoundError: (404, "donation_lot_not_found"),
    DonationQuantityInvalidError: (422, "donation_quantity_invalid"),
    DonationReceiverIncompatibleError: (409, "donation_receiver_incompatible"),
    DonationOfferConflictError: (409, "donation_offer_conflict"),
    DonationOfferNotFoundError: (404, "donation_offer_not_found"),
    DonationOfferStateError: (409, "donation_offer_state"),
    DonationStockUnavailableError: (409, "donation_stock_unavailable"),
    ReceiverInvalidError: (422, "receiver_invalid"),
    ReceiverAlreadyExistsError: (409, "receiver_already_exists"),
    ReceiverNotFoundError: (404, "receiver_not_found"),
}


REASON_EXCEPTIONS = (SourceInvalidError, SourceUrlRejectedError, SourceNotRunnableError)


def register_rescue_error_handlers(app: FastAPI) -> None:
    for exception_type, (status_code, code) in ERROR_CONTRACT.items():
        app.add_exception_handler(exception_type, _build_handler(status_code, code))


def _build_handler(status_code: int, code: str):  # type: ignore[no-untyped-def]
    def handler(_request: Request, exc: Exception) -> JSONResponse:
        content: dict[str, object] = {"code": code, "message_key": f"errors.{code}"}
        if isinstance(exc, REASON_EXCEPTIONS):
            content["details"] = {"reason": str(exc)}
        return JSONResponse(status_code=status_code, content=content)

    return handler
