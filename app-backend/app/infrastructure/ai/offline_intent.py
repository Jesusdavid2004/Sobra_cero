"""Deterministic stand-in for the language model when reading a pickup request (tests and offline demos)."""

import re

from app.application.discovery_intent_prompt import REQUEST_CLOSE_TAG, REQUEST_OPEN_TAG

THOUSAND_WORDS = {"mil", "k", "thousand"}
BUDGET_PATTERN = re.compile(
    r"(?:tengo|have|budget|presupuesto|spend|gastar|hasta|under|max)\D{0,12}?(\d+(?:[.,]\d+)?)\s*(mil|k|thousand)?",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.IGNORECASE)
QUANTITY_PATTERN = re.compile(r"(\d+)\s*(?:portions?|porciones|paquetes|packs?|panes|breads?)", re.IGNORECASE)
CATEGORY_WORDS = {
    "bakery": ("bakery", "panader", "pan "),
    "dairy": ("dairy", "lacte", "leche"),
    "produce": ("produce", "fruta", "verdura"),
    "meat": ("meat", "carne"),
    "prepared": ("meal", "comida", "almuerzo", "lunch", "prepared"),
    "pantry": ("pantry", "despensa", "drink", "bebida"),
}
MAX_CLOCK_HOUR = 12
MIDDAY_HOUR = 12
HOURS_IN_HALF_DAY = 12


def _clock(hour: str, minute: str | None, meridiem: str) -> str | None:
    value = int(hour)
    if not 1 <= value <= MAX_CLOCK_HOUR:
        return None
    pm = meridiem.lower().startswith("p")
    value = value % HOURS_IN_HALF_DAY + (HOURS_IN_HALF_DAY if pm else 0)
    return f"{value:02d}:{minute or '00'}"


def _budget(text: str) -> float | None:
    match = BUDGET_PATTERN.search(text)
    if match is None:
        return None
    amount = float(match.group(1).replace(",", "."))
    return amount * 1000 if (match.group(2) or "").lower() in THOUSAND_WORDS else amount


def read_discovery_intent_offline(prompt: str) -> dict[str, object]:
    start = prompt.find(REQUEST_OPEN_TAG)
    end = prompt.rfind(REQUEST_CLOSE_TAG)
    text = prompt[start + len(REQUEST_OPEN_TAG) : end].strip().lower() if 0 <= start < end else ""
    times = [
        value for hour, minute, meridiem in TIME_PATTERN.findall(text) if (value := _clock(hour, minute, meridiem))
    ]
    quantity = QUANTITY_PATTERN.search(text)
    category = next((name for name, words in CATEGORY_WORDS.items() if any(word in f"{text} " for word in words)), None)
    return {
        "budget": _budget(text),
        "pickup_from": times[0] if times else None,
        "pickup_until": times[1] if len(times) > 1 else None,
        "quantity": int(quantity.group(1)) if quantity else None,
        "category": category,
    }
