"""
同じ商品・ランクをできるだけ同じ箱に寄せて入庫するアルゴリズム。

出庫コストは「触れた箱の在庫総数」で課金され、あたり率（出庫枚数 ÷ 触れた箱の
在庫総数）は同じ商品が同じ箱に固まっているほど上がる。そこで入庫時に、各
(product_id, rank) を「ホーム箱」にまとめて配置し、ホーム箱が満杯になったときだけ
別の箱へ広げる。日をまたいで同じ商品が入荷しても、既存のホーム箱に追記される。

注意: これは「あたり率の最適解」を見るための配置であり、実運用では入庫時に商品ごと
仕分けする手間（=入庫工数）が増える。1日の入荷が多数の商品にまたがると、その日に
触れる箱数が増えて入庫コストが上がるトレードオフがある。
"""
from collections import defaultdict

from sim.algorithms.base import InboundAlgorithm
from sim.models import CardInfo, StorageState


class GroupByProductInbound(InboundAlgorithm):
    """同じ (product_id, rank) を同じ箱に寄せて入庫する。

    各 key について、配置先の候補をこの優先順で選ぶ:
      1. 既にその key を含む箱（=ホーム箱。空きが大きい順）
      2. 完全に空の箱（新しいホームを開く。ID 昇順）
      3. それ以外の空きがある箱（空きが大きい順）

    1 と 2 を優先することで、空き箱が残る限り key の混在を避けつつ、同じ key を
    できるだけ少ない箱にまとめる。
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

        # 作業用: 各箱の残り空き容量と、含んでいる key 集合
        avail: dict[str, int] = {sid: s.available for sid, s in storages.items()}
        capacity: dict[str, int] = {sid: s.capacity for sid, s in storages.items()}
        box_keys: dict[str, set[tuple[str, str]]] = {
            sid: {(c.product_id, c.rank) for c in s.cards}
            for sid, s in storages.items()
        }

        # 入荷カードを key ごとにまとめる
        groups: dict[tuple[str, str], list[CardInfo]] = defaultdict(list)
        for c in cards:
            groups[(c.product_id, c.rank)].append(c)

        # key を決定的な順序で処理
        for key in sorted(groups.keys()):
            batch = groups[key]
            need = len(batch)

            existing = [
                sid for sid in avail
                if avail[sid] > 0 and key in box_keys.get(sid, set())
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
                box_keys.setdefault(sid, set()).add(key)
                placed += take

            if placed < need:
                remaining = need - placed
                raise RuntimeError(
                    f"入庫できないカードが {remaining} 枚あります "
                    f"(key={key}): 空き容量が不足しています"
                )

        return assignments
