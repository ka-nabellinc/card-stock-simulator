from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Card:
    card_id: str
    product_id: str
    rank: str
    arrival_date: Optional[date] = None
    storage_id: Optional[str] = None


@dataclass
class Storage:
    storage_id: str
    capacity: int
    cards: list[Card] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.cards)

    @property
    def available_capacity(self) -> int:
        return self.capacity - len(self.cards)

    @property
    def is_full(self) -> bool:
        return len(self.cards) >= self.capacity


@dataclass(frozen=True)
class CardInfo:
    """Immutable card snapshot passed to algorithms."""
    card_id: str
    product_id: str
    rank: str
    arrival_date: Optional[date]


@dataclass(frozen=True)
class StorageState:
    """Immutable storage snapshot passed to algorithms."""
    storage_id: str
    capacity: int
    cards: tuple[CardInfo, ...]

    @property
    def count(self) -> int:
        return len(self.cards)

    @property
    def available(self) -> int:
        return self.capacity - self.count

    @property
    def is_full(self) -> bool:
        return self.count >= self.capacity


@dataclass
class Order:
    order_date: date
    product_id: str
    rank: str
    quantity: int
    order_id: str = ""


@dataclass
class DailyLog:
    date: date
    inbound_assignments: list[tuple[str, str]] = field(default_factory=list)
    outbound_assignments: list[tuple[str, str]] = field(default_factory=list)
    stocktake_moves: list[tuple[str, str]] = field(default_factory=list)
    inbound_cost_sec: float = 0.0
    outbound_cost_sec: float = 0.0
    stocktake_cost_sec: float = 0.0
    hit_rate: Optional[float] = None
    outbound_cards_count: int = 0
    outbound_total_storage_cards: int = 0

    @property
    def total_cost_sec(self) -> float:
        return self.inbound_cost_sec + self.outbound_cost_sec + self.stocktake_cost_sec
