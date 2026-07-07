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
    """できるだけ少ない箱にまとめて入庫する。

    入庫の手間（コスト）は「その日に入庫したストレージ数 × 固定秒数」で決まるため、
    1日の入庫が触れる箱数を最小化する。

    - その日の入庫カードが丸ごと収まる箱があれば、その中で空きが最も小さい箱
      （= ぴったり収まる箱）にまとめて入れる。既に使いかけの箱の空きを優先的に
      使い切ることで、空き箱を不必要に開けない。
    - 1箱に収まらない場合のみ、空き容量が大きい箱から順に詰めて箱数を最小化する。
    """

    def assign(
        self,
        cards: list[CardInfo],
        storages: dict[str, StorageState],
    ) -> list[tuple[str, str]]:
        assignments: list[tuple[str, str]] = []
        n = len(cards)
        if n == 0:
            return assignments

        def _id_key(sid: str):
            return (0, int(sid)) if sid.isdigit() else (1, sid)

        available = [s for s in storages.values() if s.available > 0]

        # 全カードが丸ごと入る箱があれば、その中で空きが最小（ぴったり）の箱にまとめる。
        fitting = [s for s in available if s.available >= n]
        if fitting:
            target = min(fitting, key=lambda s: (s.available, _id_key(s.storage_id)))
            return [(card.card_id, target.storage_id) for card in cards]

        # 1箱に収まらない場合は、空きが大きい箱から順に詰めて触れる箱数を最小化する。
        order = sorted(available, key=lambda s: (-s.available, _id_key(s.storage_id)))
        card_iter = iter(cards)
        for storage in order:
            for _ in range(storage.available):
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

        # 全カードを入庫日昇順で並べ、(product_id, rank) ごとに引けるよう索引化する。
        # 注文ごとに全在庫を走査せず該当商品のカードだけを見るための最適化で、
        # 選択順（入庫日→card_id 昇順）は全件走査と同一。
        all_cards: list[CardInfo] = []
        for storage in storages.values():
            all_cards.extend(storage.cards)
        all_cards.sort(key=lambda c: (c.arrival_date or date.min, c.card_id))

        by_key: dict[tuple[str, str], list[str]] = {}
        for card in all_cards:
            by_key.setdefault((card.product_id, card.rank), []).append(card.card_id)

        assigned: set[str] = set()
        for order in orders:
            needed = order.quantity
            for card_id in by_key.get((order.product_id, order.rank), ()):
                if needed == 0:
                    break
                if card_id not in assigned:
                    assignments.append((order, card_id))
                    assigned.add(card_id)
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

        # ストレージID昇順に全カードを並べ、(product_id, rank) ごとに索引化する。
        # 注文ごとに全在庫を走査せず該当商品のカードだけを見るための最適化で、
        # 選択順（ストレージID昇順→格納順）は全件走査と同一。
        sorted_storages = sorted(storages.values(), key=lambda s: _storage_key(s.storage_id))
        by_key: dict[tuple[str, str], list[str]] = {}
        for storage in sorted_storages:
            for card in storage.cards:
                by_key.setdefault((card.product_id, card.rank), []).append(card.card_id)

        assigned: set[str] = set()
        assignments: list[tuple[Order, str]] = []

        for order in orders:
            needed = order.quantity
            for card_id in by_key.get((order.product_id, order.rank), ()):
                if needed == 0:
                    break
                if card_id not in assigned:
                    assignments.append((order, card_id))
                    assigned.add(card_id)
                    needed -= 1

        return assignments


class NoStocktake(StocktakeAlgorithm):
    """何もしない棚卸し。常に移動なし・コスト0を返す。"""

    def execute(self, current_date, storages, order_history=None):
        return [], 0.0
