from dataclasses import dataclass
from datetime import datetime

from app.application.ai_dto import DiagnosisNarrative
from app.application.diagnosis_prompt import (
    DIAGNOSIS_PROMPT_VERSION,
    build_diagnosis_prompt,
)
from app.application.dto import Actor
from app.application.ports import AIProvider, InventoryRepository, UnitOfWork
from app.domain.diagnosis import Diagnosis, diagnose
from app.domain.entities import BatchStatus
from app.domain.exceptions import (
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIResponseInvalidError,
    ShopNotFoundError,
    WasteInvalidError,
    WasteLotNotFoundError,
    WastePermissionError,
)
from app.domain.waste import WasteEntry, WasteReason, validate_waste

NARRATIVE_AI = "ai"
NARRATIVE_QUOTA = "quota_exceeded"
NARRATIVE_UNAVAILABLE = "unavailable"
RECORDABLE_STATUSES = (BatchStatus.ACTIVE.value, BatchStatus.EXPIRED.value)
MAX_WASTE_ROWS = 100


@dataclass(frozen=True)
class WasteRecorded:
    lot_id: int
    remaining_quantity: int


@dataclass(frozen=True)
class DiagnosisResult:
    diagnosis: Diagnosis
    narrative: str | None
    narrative_status: str


def _require_business(actor: Actor) -> None:
    if not actor.can_manage_shops:
        raise WastePermissionError("Business account required")


class RecordWaste:
    """A shop declares units it could not use. Stock leaves the lot atomically and once."""

    def __init__(self, inventory: InventoryRepository, unit_of_work: UnitOfWork) -> None:
        self._inventory = inventory
        self._unit_of_work = unit_of_work

    def execute(
        self, actor: Actor, lot_id: int, quantity: int, reason: WasteReason, note: str, now: datetime
    ) -> WasteRecorded:
        _require_business(actor)
        lot = self._inventory.get_lot(lot_id)
        if (
            lot is None
            or (lot.owner_id != actor.user_id and not actor.is_admin)
            or lot.status not in RECORDABLE_STATUSES
        ):
            raise WasteLotNotFoundError("Lot not found")
        cleaned = validate_waste(quantity, lot.quantity, note)
        if not self._inventory.remove_stock(lot_id, quantity):
            self._unit_of_work.rollback()
            raise WasteInvalidError("quantity_out_of_range")
        self._inventory.add_waste(lot_id, quantity, reason.value, cleaned, actor.user_id, now)
        self._unit_of_work.commit()
        return WasteRecorded(lot_id, lot.quantity - quantity)


class ListShopWaste:
    def __init__(self, inventory: InventoryRepository) -> None:
        self._inventory = inventory

    def execute(self, actor: Actor, shop_id: int) -> list[WasteEntry]:
        _require_business(actor)
        owner = self._inventory.get_shop_owner(shop_id)
        if owner is None or (owner != actor.user_id and not actor.is_admin):
            raise ShopNotFoundError("Shop not found")
        return self._inventory.list_waste(shop_id, MAX_WASTE_ROWS)


class DiagnoseShop:
    """Numbers and alerts come from code. The model only words them, and the result still stands without it."""

    def __init__(self, inventory: InventoryRepository, ai_provider: AIProvider) -> None:
        self._inventory = inventory
        self._ai_provider = ai_provider

    def execute(self, actor: Actor, shop_id: int, language: str, now: datetime) -> DiagnosisResult:
        _require_business(actor)
        owner = self._inventory.get_shop_owner(shop_id)
        if owner is None or (owner != actor.user_id and not actor.is_admin):
            raise ShopNotFoundError("Shop not found")
        diagnosis = diagnose(self._inventory.snapshot(shop_id, now), now)
        try:
            narrative = self._ai_provider.generate_structured(
                prompt=build_diagnosis_prompt(diagnosis, language),
                response_model=DiagnosisNarrative,
                user_id=actor.user_id,
                locale=language,
                prompt_version=DIAGNOSIS_PROMPT_VERSION,
                model_tier="fast",
            )
        except AIQuotaExceededError:
            return DiagnosisResult(diagnosis, None, NARRATIVE_QUOTA)
        except (AIProviderUnavailableError, AIResponseInvalidError):
            return DiagnosisResult(diagnosis, None, NARRATIVE_UNAVAILABLE)
        return DiagnosisResult(diagnosis, narrative.text, NARRATIVE_AI)
