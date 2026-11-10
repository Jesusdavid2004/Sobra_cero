"""Centralized mapping from domain exceptions to the { code, message_key } error contract."""

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.domain.exceptions import (
    InvalidRescuePlanTransitionError,
    LotNotRescuableError,
    RescueLotNotFoundError,
    RescuePermissionError,
    RescuePlanConflictError,
    RescuePlanNotFoundError,
    RescuePlanStaleError,
)

ERROR_CONTRACT: dict[type[Exception], tuple[int, str]] = {
    RescuePermissionError: (403, "rescue_permission_denied"),
    RescueLotNotFoundError: (404, "rescue_lot_not_found"),
    RescuePlanNotFoundError: (404, "rescue_plan_not_found"),
    LotNotRescuableError: (409, "rescue_lot_not_rescuable"),
    RescuePlanStaleError: (409, "rescue_plan_stale"),
    InvalidRescuePlanTransitionError: (409, "rescue_plan_invalid_transition"),
    RescuePlanConflictError: (409, "rescue_plan_conflict"),
}


def register_rescue_error_handlers(app: FastAPI) -> None:
    for exception_type, (status_code, code) in ERROR_CONTRACT.items():
        app.add_exception_handler(exception_type, _build_handler(status_code, code))


def _build_handler(status_code: int, code: str):  # type: ignore[no-untyped-def]
    def handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"code": code, "message_key": f"errors.{code}"})

    return handler
