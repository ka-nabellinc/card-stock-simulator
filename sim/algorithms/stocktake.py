"""棚卸し関連アルゴリズム集。"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sim.algorithms.base import InboundAlgorithm, StocktakeAlgorithm
from sim.models import CardInfo, Order, StorageState


class Top100ReservedInbound(InboundAlgorithm):
    """TOP100棚卸し専用ストレージを除外して入庫する。

    target_storages（デフォルト: 1〜10番）を棚卸し専用枠として確保し、
    通常入庫では使わない。それ以外は FillEmptyStorageInbound と同じロジック。
    """

    def __init__(
        self,
        reserved_storages: list[int] | None = None,
        **kwargs,
    ):
        self.reserved_ids: set[str] = (
            {str(s) for s in reserved_storages}
            if reserved_storages is not None
            else {str(i) for i in range(1, 11)}
        )

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

        # 予約済みストレージを除外
        available = [
            s for s in storages.values()
            if s.available > 0 and s.storage_id not in self.reserved_ids
        ]

        fitting = [s for s in available if s.available >= n]
        if fitting:
            target = min(fitting, key=lambda s: (s.available, _id_key(s.storage_id)))
            return [(card.card_id, target.storage_id) for card in cards]

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


class Top100WeeklyStocktake(StocktakeAlgorithm):
    """直近1ヶ月の売れ筋TOP N種を指定ストレージに集める週次棚卸し。

    毎週 weekday（デフォルト: 月曜=0）に実行し、
    直近 lookback_days 日間の出庫実績から売れ筋 top_n 種を集計して
    target_storages（デフォルト: 1〜10番）に cards_per_type 枚ずつ集める。
    """

    def __init__(
        self,
        top_n: int = 100,
        cards_per_type: int = 4,
        lookback_days: int = 30,
        weekday: int = 0,
        target_storages: list[int] | None = None,
        move_per_card_sec: float = 30.0,
        **kwargs,
    ):
        self.top_n = top_n
        self.cards_per_type = cards_per_type
        self.lookback_days = lookback_days
        self.weekday = weekday
        self.target_storage_ids = (
            [str(s) for s in target_storages]
            if target_storages is not None
            else [str(i) for i in range(1, 11)]
        )
        self.move_per_card_sec = move_per_card_sec

    def execute(
        self,
        current_date: date,
        storages: dict[str, StorageState],
        order_history: list[tuple[date, Order]] | None = None,
    ) -> tuple[list[tuple[str, str]], float]:
        if current_date.weekday() != self.weekday:
            return [], 0.0

        if not order_history:
            return [], 0.0

        # 直近 lookback_days 日の出庫から売れ筋を集計
        cutoff = current_date - timedelta(days=self.lookback_days)
        counter: Counter[tuple[str, str]] = Counter()
        for order_date, order in order_history:
            if order_date >= cutoff:
                counter[(order.product_id, order.rank)] += order.quantity

        top_types: set[tuple[str, str]] = {
            key for key, _ in counter.most_common(self.top_n)
        }
        if not top_types:
            return [], 0.0

        target_set = set(self.target_storage_ids)

        # ターゲットストレージにすでにある対象カードを確認
        already: dict[tuple[str, str], list[str]] = defaultdict(list)
        for sid in self.target_storage_ids:
            if sid not in storages:
                continue
            for card in storages[sid].cards:
                key = (card.product_id, card.rank)
                if key in top_types:
                    already[key].append(card.card_id)

        # 他ストレージにある対象カードをタイプ別に収集
        other: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for sid, storage in storages.items():
            if sid in target_set:
                continue
            for card in storage.cards:
                key = (card.product_id, card.rank)
                if key in top_types:
                    other[key].append((card.card_id, sid))

        # ターゲットストレージの空き容量を追跡
        free: dict[str, int] = {
            sid: storages[sid].available
            for sid in self.target_storage_ids
            if sid in storages
        }

        moves: list[tuple[str, str]] = []

        for key in top_types:
            needed = self.cards_per_type - len(already.get(key, []))
            if needed <= 0:
                continue
            for card_id, _src in other.get(key, []):
                if needed <= 0:
                    break
                # 空きのあるターゲットストレージを先頭から探す
                dest = next(
                    (sid for sid in self.target_storage_ids if free.get(sid, 0) > 0),
                    None,
                )
                if dest is None:
                    break  # ターゲットストレージが全て満杯
                moves.append((card_id, dest))
                free[dest] -= 1
                needed -= 1

        cost = len(moves) * self.move_per_card_sec
        return moves, cost
