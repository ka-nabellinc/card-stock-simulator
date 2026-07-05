"""在庫の少ない箱から優先して出庫するアルゴリズム。

あたり率 = 出庫枚数 ÷ 触れた箱の在庫総数 なので、在庫（＝分母）が最も小さい箱から
順に開けて需要を満たせば、あたり率を最大化しやすい。

集約（ConsolidatedStorageOutbound）が「限界コスト ÷ カバーできる需要」で箱を選ぶのに
対し、こちらは純粋に在庫数の少なさだけで箱を選ぶ「あたり率特化」の対照アルゴリズム。
一度開けた箱からはカバーできる需要をすべて取り切る（在庫課金は箱ごとに1回のため）。
"""
from collections import defaultdict

from sim.algorithms.base import OutboundAlgorithm
from sim.models import Order, StorageState


class LowInventoryFirstOutbound(OutboundAlgorithm):
    """在庫数が最も少ない箱から順に開けて出庫する。"""

    def select(
        self,
        orders: list[Order],
        storages: dict[str, StorageState],
    ) -> list[tuple[Order, str]]:
        assignments: list[tuple[Order, str]] = []
        if not orders:
            return assignments

        def _id_key(sid: str):
            return (0, int(sid)) if sid.isdigit() else (1, sid)

        # ---- 需要を (product_id, rank) 単位に集計し、注文への割り当て口を用意 ----
        demand: dict[tuple[str, str], int] = defaultdict(int)
        orders_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
        order_need: list[int] = []
        for idx, o in enumerate(orders):
            key = (o.product_id, o.rank)
            demand[key] += o.quantity
            orders_by_key[key].append(idx)
            order_need.append(o.quantity)

        order_ptr: dict[tuple[str, str], int] = defaultdict(int)

        def _next_order_idx(key: tuple[str, str]) -> int | None:
            lst = orders_by_key[key]
            p = order_ptr[key]
            while p < len(lst) and order_need[lst[p]] == 0:
                p += 1
            order_ptr[key] = p
            return lst[p] if p < len(lst) else None

        # ---- 各箱の、需要に一致する取り出し可能カードを集める ----
        # sid -> (箱の在庫総数, key -> [card_id, ...])
        avail: dict[str, tuple[int, dict[tuple[str, str], list[str]]]] = {}
        for sid, s in storages.items():
            matched: dict[tuple[str, str], list[str]] = defaultdict(list)
            for c in s.cards:
                key = (c.product_id, c.rank)
                if key in demand:
                    matched[key].append(c.card_id)
            if matched:
                avail[sid] = (s.count, matched)

        # ---- 在庫数昇順（同点はID昇順）で箱を開け、需要が残る限りカバーを取り切る ----
        for sid in sorted(avail, key=lambda s: (avail[s][0], _id_key(s))):
            if not any(v > 0 for v in demand.values()):
                break
            _count, matched = avail[sid]
            for key, card_ids in matched.items():
                while demand[key] > 0 and card_ids:
                    order_idx = _next_order_idx(key)
                    if order_idx is None:
                        break
                    cid = card_ids.pop()
                    assignments.append((orders[order_idx], cid))
                    order_need[order_idx] -= 1
                    demand[key] -= 1

        return assignments
