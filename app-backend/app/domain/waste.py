"""Waste that a shop declares. It is only what the shop records; nothing here estimates waste."""

from enum import StrEnum

from app.domain.exceptions import WasteInvalidError

MAX_WASTE_NOTE_CHARS = 200


class WasteReason(StrEnum):
    EXPIRED = "expired"
    DAMAGED = "damaged"
    UNSOLD = "unsold"
    OTHER = "other"


def validate_waste(quantity: int, available: int, note: str) -> str:
    """Return the cleaned note, or raise when the quantity or the note cannot be recorded."""
    if not 1 <= quantity <= available:
        raise WasteInvalidError("quantity_out_of_range")
    cleaned = " ".join(note.split())
    if len(cleaned) > MAX_WASTE_NOTE_CHARS:
        raise WasteInvalidError("note_too_long")
    return cleaned
