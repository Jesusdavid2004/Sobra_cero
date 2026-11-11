"""Ordered history of a lot: what was recommended, decided and then actually happened.

Reservations appear only as units and times: no customer identity is ever part of the timeline.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.domain.entities import ReservationStatus


class TimelineEventKind(StrEnum):
    PLAN_GENERATED = "plan_generated"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    DISCOUNT_APPLIED = "discount_applied"
    ANALYSIS_FALLBACK = "analysis_fallback"
    RESERVED = "reserved"
    PICKED_UP = "picked_up"
    RESERVATION_CANCELLED = "reservation_cancelled"
    RESERVATION_EXPIRED = "reservation_expired"
    DONATED = "donated"


PLAN_EVENT_KINDS = {
    "generated": TimelineEventKind.PLAN_GENERATED,
    "approved": TimelineEventKind.PLAN_APPROVED,
    "rejected": TimelineEventKind.PLAN_REJECTED,
    "discount_applied": TimelineEventKind.DISCOUNT_APPLIED,
    "analysis_fallback": TimelineEventKind.ANALYSIS_FALLBACK,
}

RESERVATION_END_KINDS = {
    ReservationStatus.PICKED_UP.value: TimelineEventKind.PICKED_UP,
    ReservationStatus.CANCELLED.value: TimelineEventKind.RESERVATION_CANCELLED,
    ReservationStatus.EXPIRED.value: TimelineEventKind.RESERVATION_EXPIRED,
}


@dataclass(frozen=True)
class PlanEventRow:
    plan_id: int
    event_type: str
    occurred_at: datetime
    payload_json: str


@dataclass(frozen=True)
class ReservationRow:
    units: int
    status: str
    created_at: datetime
    status_changed_at: datetime | None


@dataclass(frozen=True)
class DonationRow:
    units: int
    created_at: datetime


@dataclass(frozen=True)
class TimelineEvent:
    kind: TimelineEventKind
    occurred_at: datetime
    plan_id: int | None = None
    units: int | None = None
    discount_percent: int | None = None


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _payload(raw: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _plan_events(rows: Iterable[PlanEventRow]) -> list[TimelineEvent]:
    events = []
    for row in rows:
        kind = PLAN_EVENT_KINDS.get(row.event_type)
        if kind is None:
            continue
        discount = _payload(row.payload_json).get("discount_percent")
        events.append(
            TimelineEvent(
                kind,
                _utc(row.occurred_at),
                plan_id=row.plan_id,
                discount_percent=discount if isinstance(discount, int) else None,
            )
        )
    return events


def _reservation_events(rows: Iterable[ReservationRow]) -> list[TimelineEvent]:
    events = []
    for row in rows:
        events.append(TimelineEvent(TimelineEventKind.RESERVED, _utc(row.created_at), units=row.units))
        end_kind = RESERVATION_END_KINDS.get(row.status)
        if end_kind is not None:
            ended_at = row.status_changed_at or row.created_at
            events.append(TimelineEvent(end_kind, _utc(ended_at), units=row.units))
    return events


def build_timeline(
    plan_events: Iterable[PlanEventRow],
    reservations: Iterable[ReservationRow],
    donations: Iterable[DonationRow],
) -> tuple[TimelineEvent, ...]:
    events = _plan_events(plan_events) + _reservation_events(reservations)
    events += [TimelineEvent(TimelineEventKind.DONATED, _utc(row.created_at), units=row.units) for row in donations]
    return tuple(sorted(events, key=lambda event: event.occurred_at))
