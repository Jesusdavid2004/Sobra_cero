from dataclasses import dataclass


@dataclass(frozen=True)
class PublicShop:
    """What anyone may see about a shop. Owner and account data are not part of it."""

    id: int
    name: str
    description: str
    business_type: str
    latitude: float
    longitude: float
