"""Conversions between application DTOs and the generated gRPC messages."""

from datetime import date

from app.application.dto import (
    DailySales,
    LotAnalysis,
    LotAnalysisInput,
    SalesForecastModelArtifact,
)
from app.domain.exceptions import InvalidAnalysisRequestError
from app.domain.rescue import RescueAction, RescueReason
from app.infrastructure.analysis.generated import rescue_analysis_pb2 as pb


def snapshot_to_proto(lot: LotAnalysisInput) -> pb.LotSnapshot:
    message = pb.LotSnapshot(
        lot_ref=lot.lot_ref,
        available_quantity=lot.available_quantity,
        current_discount_percent=lot.current_discount_percent,
        horizon_hours=lot.horizon_hours,
        as_of_date=lot.as_of_date.isoformat(),
        history=[
            pb.DailySales(
                sales_date=entry.sales_date.isoformat(),
                units_sold=entry.units_sold,
                had_promotion=entry.had_promotion,
            )
            for entry in lot.history
        ],
    )
    if lot.model is not None:
        message.model.CopyFrom(pb.WeekdayModel(version=lot.model.version, weekday_factors=lot.model.weekday_factors))
    return message


def snapshot_from_proto(message: pb.LotSnapshot) -> LotAnalysisInput:
    try:
        as_of = date.fromisoformat(message.as_of_date)
        history = [
            DailySales(date.fromisoformat(entry.sales_date), entry.units_sold, entry.had_promotion)
            for entry in message.history
        ]
    except ValueError as exc:
        raise InvalidAnalysisRequestError("Dates must be ISO-8601") from exc
    model = (
        SalesForecastModelArtifact(
            version=message.model.version,
            weekday_factors=tuple(message.model.weekday_factors),
            trained_until=as_of,
        )
        if message.HasField("model")
        else None
    )
    return LotAnalysisInput(
        lot_ref=message.lot_ref,
        available_quantity=message.available_quantity,
        current_discount_percent=message.current_discount_percent,
        horizon_hours=message.horizon_hours,
        as_of_date=as_of,
        history=history,
        model=model,
    )


def analysis_to_proto(analysis: LotAnalysis) -> pb.LotAnalysis:
    message = pb.LotAnalysis(
        lot_ref=analysis.lot_ref,
        expected_sales=analysis.expected_sales,
        surplus_units=analysis.surplus_units,
        action=analysis.action.value,
        reasons=[reason.value for reason in analysis.reasons],
        model_version=analysis.model_version,
        rule_version=analysis.rule_version,
        horizon_days_used=analysis.horizon_days_used,
    )
    if analysis.proposed_discount_percent is not None:
        message.proposed_discount_percent = analysis.proposed_discount_percent
    return message


def analysis_from_proto(message: pb.LotAnalysis, source: str) -> LotAnalysis:
    return LotAnalysis(
        lot_ref=message.lot_ref,
        expected_sales=message.expected_sales,
        surplus_units=message.surplus_units,
        action=RescueAction(message.action),
        proposed_discount_percent=(
            message.proposed_discount_percent if message.HasField("proposed_discount_percent") else None
        ),
        reasons=tuple(RescueReason(reason) for reason in message.reasons),
        model_version=message.model_version,
        rule_version=message.rule_version,
        horizon_days_used=message.horizon_days_used,
        source=source,
    )
