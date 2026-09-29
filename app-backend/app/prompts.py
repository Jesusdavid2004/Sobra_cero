"""Prompt templates used for promotional text generation.

Templates are stored here (not inline) so the exact prompt sent to the model
can be persisted alongside each generated promotion for auditability.
"""

from __future__ import annotations

from app.models import Lot

VARIANTS = ("urgency", "savings", "sustainability")

SYSTEM_PROMPT = "You are a food-rescue marketing copywriter."

TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "urgency": "Write ONE short promotional message in English for this food-rescue lot. Focus on urgency: it expires soon and stock is limited. Maximum 25 words.",  # noqa: E501
        "savings": "Write ONE short promotional message in English for this food-rescue lot. Focus on the discount and value for money. Maximum 25 words.",  # noqa: E501
        "sustainability": "Write ONE short promotional message in English for this food-rescue lot. Focus on reducing food waste. Maximum 25 words.",  # noqa: E501
    },
    "es": {
        "urgency": "Escribe UN mensaje promocional corto en espanol para este lote de comida rescatada. Enfocate en la urgencia: caduca pronto y el stock es limitado. Maximo 25 palabras.",  # noqa: E501
        "savings": "Escribe UN mensaje promocional corto en espanol para este lote de comida rescatada. Enfocate en el descuento y la relacion calidad-precio. Maximo 25 palabras.",  # noqa: E501
        "sustainability": "Escribe UN mensaje promocional corto en espanol para este lote de comida rescatada. Enfocate en reducir el desperdicio de comida. Maximo 25 palabras.",  # noqa: E501
    },
}


def build_prompt(lot: Lot, language: str, variant: str) -> str:
    """Compose the prompt for a single promotional variant of a lot."""
    discounted_price = max(0, lot.original_price_cents * (100 - lot.discount_percent) // 100)
    details = (
        f"Lot: {lot.title}\n"
        f"Description: {lot.description}\n"
        f"Original price (cents): {lot.original_price_cents}\n"
        f"Discounted price (cents): {discounted_price}\n"
        f"Discount: {lot.discount_percent}%\n"
        f"Quantity available: {lot.quantity}\n"
        f"Expires at: {lot.expires_at.isoformat()}\n"
    )
    template = TEMPLATES.get(language, TEMPLATES["en"])[variant]
    return f"{template}\n\n{details}"
