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
    ReceiverAlreadyExistsError,
    ReceiverInvalidError,
    ReceiverNotFoundError,
    RescueLotNotFoundError,
    RescuePermissionError,
    RescuePlanConflictError,
    RescuePlanNotFoundError,
    RescuePlanStaleError,
    ShopNotFoundError,
    SimulationInvalidError,
    SimulationUnavailableError,
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


def register_rescue_error_handlers(app: FastAPI) -> None:
    for exception_type, (status_code, code) in ERROR_CONTRACT.items():
        app.add_exception_handler(exception_type, _build_handler(status_code, code))


def _build_handler(status_code: int, code: str):  # type: ignore[no-untyped-def]
    def handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"code": code, "message_key": f"errors.{code}"})

    return handler
