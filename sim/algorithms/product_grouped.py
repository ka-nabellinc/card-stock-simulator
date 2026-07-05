"""同じ商品(product_id)を、ランクを問わず同じ箱へ寄せて入庫するアルゴリズム。

GroupByProductInbound が (product_id, rank) 単位でホーム箱を作るのに対し、こちらは
product_id 単位でまとめる（同じ商品なら別ランクでも同じホーム箱に入れる）。ホーム箱の
数が商品数まで減るぶん、grouped より入庫時に触れる箱数が少なく入庫工数を抑えやすい。
注文は (product_id, rank) で来るため、同一商品が1箱に集まっているほど、その箱を開けて
複数ランクの注文をまとめてカバーでき、あたり率も稼ぎやすい。FillEmpty(集約なし)と
grouped(商品×ランクで完全集約)の中間に位置する集約入庫。
"""
from collections import defaultdict

from sim.algorithms.base import InboundAlgorithm
from sim.models import CardInfo, StorageState


class ProductGroupedInbound(InboundAlgorithm):
    """同じ product_id を同じ箱に寄せて入庫する（ランクは混在を許容）。

    各 product_id について、配置先の候補をこの優先順で選ぶ:
      1. 既にその product_id を含む箱（=ホーム箱。空きが大きい順）
      2. 完全に空の箱（新しいホームを開く。ID 昇順）
      3. それ以外の空きがある箱（空きが大きい順）
    """

    def assign(
        self,
        cards: list[CardInfo],
        storages: dict[str, StorageState],
    ) -> list[tuple[str, str]]:
        assignments: list[tuple[str, str]] = []
        if not cards:
            return assignments

        def _id_key(sid: str):
            return (0, int(sid)) if sid.isdigit() else (1, sid)

        avail: dict[str, int] = {sid: s.available for sid, s in storages.items()}
        capacity: dict[str, int] = {sid: s.capacity for sid, s in storages.items()}
        box_products: dict[str, set[str]] = {
            sid: {c.product_id for c in s.cards}
            for sid, s in storages.items()
        }

        # 入荷カードを product_id ごとにまとめる
        groups: dict[str, list[CardInfo]] = defaultdict(list)
        for c in cards:
            groups[c.product_id].append(c)

        for pid in sorted(groups.keys()):
            batch = groups[pid]
            need = len(batch)

            existing = [
                sid for sid in avail
                if avail[sid] > 0 and pid in box_products.get(sid, set())
            ]
            existing.sort(key=lambda sid: (-avail[sid], _id_key(sid)))

            empties = [
                sid for sid in avail
                if avail[sid] > 0 and avail[sid] == capacity[sid]
            ]
            empties.sort(key=_id_key)

            existing_set = set(existing)
            others = [
                sid for sid in avail
                if avail[sid] > 0
                and sid not in existing_set
                and avail[sid] != capacity[sid]
            ]
            others.sort(key=lambda sid: (-avail[sid], _id_key(sid)))

            order = existing + empties + others

            it = iter(batch)
            placed = 0
            for sid in order:
                if placed >= need:
                    break
                space = avail[sid]
                if space <= 0:
                    continue
                take = min(space, need - placed)
                for _ in range(take):
                    c = next(it)
                    assignments.append((c.card_id, sid))
                avail[sid] -= take
                box_products.setdefault(sid, set()).add(pid)
                placed += take

            if placed < need:
                remaining = need - placed
                raise RuntimeError(
                    f"入庫できないカードが {remaining} 枚あります "
                    f"(product_id={pid}): 空き容量が不足しています"
                )

        return assignments
