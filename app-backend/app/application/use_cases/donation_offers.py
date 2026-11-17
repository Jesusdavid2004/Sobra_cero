from dataclasses import dataclass
from datetime import datetime, timedelta

from app.application.ai_dto import DonationOfferDraft
from app.application.donation_offer_prompt import (
    DONATION_OFFER_PROMPT_VERSION,
    build_donation_offer_prompt,
)
from app.application.dto import Actor
from app.application.ports import AIProvider, DonationRepository, UnitOfWork
from app.domain.entities import BatchStatus
from app.domain.exceptions import (
    DonationLotNotFoundError,
    DonationOfferNotFoundError,
    DonationOfferStateError,
    DonationPermissionError,
    DonationQuantityInvalidError,
    DonationReceiverIncompatibleError,
    DonationStockUnavailableError,
    ReceiverNotFoundError,
)
from app.domain.receivers import (
    DonationLot,
    DonationOffer,
    OfferStatus,
    OfferView,
    Receiver,
    ReceiverAssessment,
    assess_receiver,
    rank_receivers,
)
from app.domain.rules import RECEIVER_FAIRNESS_LOOKBACK_DAYS, RECEIVER_MATCH_RADIUS_KM


@dataclass(frozen=True)
class ReceiverMatches:
    compatible: tuple[ReceiverAssessment, ...]
    excluded: tuple[ReceiverAssessment, ...]


def _require_shop(actor: Actor) -> None:
    if not actor.can_manage_shops:
        raise DonationPermissionError("Business account required")


def _owned_open_lot(donations: DonationRepository, actor: Actor, lot_id: int, now: datetime) -> DonationLot:
    lot = donations.get_lot(lot_id)
    owned = lot is not None and (lot.owner_id == actor.user_id or actor.is_admin)
    if lot is None or not owned or lot.status != BatchStatus.ACTIVE.value or lot.closes_at <= now:
        raise DonationLotNotFoundError("Lot is not open for donation")
    return lot


def _check_quantity(lot: DonationLot, quantity: int) -> None:
    if not 1 <= quantity <= lot.available_quantity:
        raise DonationQuantityInvalidError("Quantity must be between one and the units available")


def _assess_all(
    donations: DonationRepository, receivers: list[Receiver], lot: DonationLot, quantity: int, now: datetime
) -> list[ReceiverAssessment]:
    recent = donations.recent_committed_counts(now - timedelta(days=RECEIVER_FAIRNESS_LOOKBACK_DAYS))
    return [
        assess_receiver(receiver, lot, quantity, now, recent.get(receiver.id, 0), RECEIVER_MATCH_RADIUS_KM)
        for receiver in receivers
    ]


class FindDonationReceivers:
    """List receivers that can take a lot (hard rules), ordered fairly, and explain who was left out."""

    def __init__(self, donations: DonationRepository) -> None:
        self._donations = donations

    def execute(self, actor: Actor, lot_id: int, quantity: int, now: datetime) -> ReceiverMatches:
        _require_shop(actor)
        lot = _owned_open_lot(self._donations, actor, lot_id, now)
        _check_quantity(lot, quantity)
        assessments = _assess_all(self._donations, self._donations.list_receivers(), lot, quantity, now)
        excluded = [item for item in assessments if not item.compatible]
        return ReceiverMatches(tuple(rank_receivers(assessments)), tuple(excluded))


class CreateDonationOffer:
    """Offer part of a lot to one compatible receiver. Stock is only committed when they accept."""

    def __init__(self, donations: DonationRepository, unit_of_work: UnitOfWork) -> None:
        self._donations = donations
        self._unit_of_work = unit_of_work

    def execute(
        self, actor: Actor, lot_id: int, receiver_id: int, quantity: int, message: str, now: datetime
    ) -> DonationOffer:
        _require_shop(actor)
        lot = _owned_open_lot(self._donations, actor, lot_id, now)
        _check_quantity(lot, quantity)
        receiver = self._donations.get_receiver(receiver_id)
        if receiver is None:
            raise ReceiverNotFoundError("Receiver not found")
        assessment = _assess_all(self._donations, [receiver], lot, quantity, now)[0]
        if not assessment.compatible:
            raise DonationReceiverIncompatibleError("This receiver cannot take the lot right now")
        offer = self._donations.add_offer(lot_id, receiver_id, quantity, message.strip(), now)
        self._unit_of_work.commit()
        return offer


class DraftDonationMessage:
    """Word a courteous message for the owner to review. The model never sees or decides quantities."""

    def __init__(self, donations: DonationRepository, ai_provider: AIProvider) -> None:
        self._donations = donations
        self._ai_provider = ai_provider

    def execute(self, actor: Actor, lot_id: int, receiver_id: int, language: str, now: datetime) -> str:
        _require_shop(actor)
        lot = _owned_open_lot(self._donations, actor, lot_id, now)
        receiver = self._donations.get_receiver(receiver_id)
        if receiver is None:
            raise ReceiverNotFoundError("Receiver not found")
        draft = self._ai_provider.generate_structured(
            prompt=build_donation_offer_prompt(lot.title, lot.category, receiver.name, language),
            response_model=DonationOfferDraft,
            user_id=actor.user_id,
            locale=language,
            prompt_version=DONATION_OFFER_PROMPT_VERSION,
            model_tier="fast",
        )
        return draft.text


class RespondToDonationOffer:
    """The receiver accepts or declines. Accepting commits the units atomically, once."""

    def __init__(self, donations: DonationRepository, unit_of_work: UnitOfWork) -> None:
        self._donations = donations
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, offer_id: int, accept: bool, now: datetime) -> DonationOffer:
        offer = self._donations.get_offer(offer_id)
        receiver = self._donations.get_receiver(offer.receiver_id) if offer else None
        if offer is None or receiver is None or receiver.owner_user_id != actor.user_id:
            raise DonationOfferNotFoundError("Offer not found")
        target = OfferStatus.ACCEPTED if accept else OfferStatus.DECLINED
        if not self._donations.claim_offer(offer_id, OfferStatus.OFFERED, target, now):
            self._unit_of_work.rollback()
            raise DonationOfferStateError("This offer was already answered")
        if accept and not self._donations.commit_stock(offer.lot_id, offer.quantity, now):
            self._unit_of_work.rollback()
            raise DonationStockUnavailableError("The offered units are no longer available")
        self._unit_of_work.commit()
        answered = self._donations.get_offer(offer_id)
        assert answered is not None
        return answered


class ConfirmDonationDelivery:
    """The shop confirms the handover. Only delivered offers count as donated units."""

    def __init__(self, donations: DonationRepository, unit_of_work: UnitOfWork) -> None:
        self._donations = donations
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, offer_id: int, now: datetime) -> DonationOffer:
        _require_shop(actor)
        offer = self._donations.get_offer(offer_id)
        lot = self._donations.get_lot(offer.lot_id) if offer else None
        if offer is None or lot is None or (lot.owner_id != actor.user_id and not actor.is_admin):
            raise DonationOfferNotFoundError("Offer not found")
        if not self._donations.claim_offer(offer_id, OfferStatus.ACCEPTED, OfferStatus.DELIVERED, now):
            self._unit_of_work.rollback()
            raise DonationOfferStateError("Only an accepted offer can be marked as delivered")
        self._donations.record_delivery(offer.lot_id, offer.quantity)
        self._unit_of_work.commit()
        delivered = self._donations.get_offer(offer_id)
        assert delivered is not None
        return delivered


class RegisterReceiver:
    def __init__(self, donations: DonationRepository, unit_of_work: UnitOfWork) -> None:
        self._donations = donations
        self._unit_of_work = unit_of_work

    def execute(self, receiver: Receiver) -> Receiver:
        saved = self._donations.add_receiver(receiver)
        self._unit_of_work.commit()
        return saved


class GetMyReceiver:
    def __init__(self, donations: DonationRepository) -> None:
        self._donations = donations

    def execute(self, actor: Actor) -> Receiver:
        receiver = self._donations.get_receiver_by_owner(actor.user_id)
        if receiver is None:
            raise ReceiverNotFoundError("No receiver profile")
        return receiver


class ListReceiverOffers:
    def __init__(self, donations: DonationRepository) -> None:
        self._donations = donations

    def execute(self, actor: Actor) -> list[OfferView]:
        receiver = self._donations.get_receiver_by_owner(actor.user_id)
        if receiver is None:
            raise ReceiverNotFoundError("No receiver profile")
        return self._donations.view_offers_for_receiver(receiver.id)


class ListLotDonationOffers:
    def __init__(self, donations: DonationRepository) -> None:
        self._donations = donations

    def execute(self, actor: Actor, lot_id: int) -> list[OfferView]:
        _require_shop(actor)
        lot = self._donations.get_lot(lot_id)
        if lot is None or (lot.owner_id != actor.user_id and not actor.is_admin):
            raise DonationLotNotFoundError("Lot not found")
        return self._donations.view_offers_for_lot(lot_id)
