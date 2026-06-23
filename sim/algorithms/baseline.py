"""
Baseline algorithms for the warehouse simulation.

- FillEmptyStorageInbound: 空きストレージから順に入庫する。
- OldestFirstOutbound: 最古の入庫日のカードから優先的に出庫する。
- NoStocktake: 何もしない棚卸し。
"""
from datetime import date

from sim.algorithms.base import InboundAlgorithm, OutboundAlgorithm, StocktakeAlgorithm
from sim.models import CardInfo, Order, StorageState


class FillEmptyStorageInbound(InboundAlgorithm):
    """空いているストレージIDに順番に入庫する。"""

    def assign(
        self,
        cards: list[CardInfo],
        storages: dict[str, StorageState],
    ) -> list[tuple[str, str]]:
        assignments: list[tuple[str, str]] = []

        # 空き容量のあるストレージをID順に並べる
        available = sorted(
            [s for s in storages.values() if s.available > 0],
            key=lambda s: s.storage_id,
        )

        card_iter = iter(cards)
        for storage in available:
            slots = storage.available
            for _ in range(slots):
                try:
                    card = next(card_iter)
                except StopIteration:
                    return assignments
                assignments.append((card.card_id, storage.storage_id))

        remaining = list(card_iter)
        if remaining:
            raise RuntimeError(
                f"入庫できないカードが {len(remaining)} 枚あります: "
                f"{[c.card_id for c in remaining]}"
            )

        return assignments


class OldestFirstOutbound(OutboundAlgorithm):
    """最古の入庫日のカードから優先的に出庫する（FIFO）。"""

    def select(
        self,
        orders: list[Order],
        storages: dict[str, StorageState],
    ) -> list[tuple[Order, str]]:
        assignments: list[tuple[Order, str]] = []

        # 全カードを入庫日昇順で並べる
        all_cards: list[CardInfo] = []
        for storage in storages.values():
            all_cards.extend(storage.cards)
        all_cards.sort(key=lambda c: (c.arrival_date or date.min, c.card_id))

        for order in orders:
            needed = order.quantity
            for card in all_cards:
                if needed == 0:
                    break
                if card.product_id == order.product_id and card.rank == order.rank:
                    # まだ割り当てられていないか確認
                    already_assigned = any(c == card.card_id for _, c in assignments)
                    if not already_assigned:
                        assignments.append((order, card.card_id))
                        needed -= 1

        return assignments


class SmallestStorageFirstOutbound(OutboundAlgorithm):
    """ストレージIDが小さい順にカードを選んで出庫する。"""

    def select(
        self,
        orders: list[Order],
        storages: dict[str, StorageState],
    ) -> list[tuple[Order, str]]:
        def _storage_key(sid: str):
            return int(sid) if sid.isdigit() else sid

        # ストレージID昇順に全カードを並べる
        sorted_storages = sorted(storages.values(), key=lambda s: _storage_key(s.storage_id))
        all_cards: list[tuple[str, CardInfo]] = []
        for storage in sorted_storages:
            for card in storage.cards:
                all_cards.append((storage.storage_id, card))

        assigned: set[str] = set()
        assignments: list[tuple[Order, str]] = []

        for order in orders:
            needed = order.quantity
            for _sid, card in all_cards:
                if needed == 0:
                    break
                if card.card_id in assigned:
                    continue
                if card.product_id == order.product_id and card.rank == order.rank:
                    assignments.append((order, card.card_id))
                    assigned.add(card.card_id)
                    needed -= 1

        return assignments


class NoStocktake(StocktakeAlgorithm):
    """何もしない棚卸し。常に移動なし・コスト0を返す。"""

    def execute(
        self,
        current_date: date,
        storages: dict[str, StorageState],
    ) -> tuple[list[tuple[str, str]], float]:
        return [], 0.0
