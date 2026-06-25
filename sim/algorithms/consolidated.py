"""
できるだけ少ないストレージにまとめて出庫するアルゴリズム。

出庫コストは

    出庫コスト = 触れたストレージ数 × pick_per_storage_sec
              + Σ(触れたストレージの在庫総数) × per_card_sec

で決まる（取り出した枚数ではなく、触れた箱の在庫総数で課金される）。
したがって、

  1. 触れる箱の数を減らす（1日の注文を少数の箱に寄せる）
  2. 触れるなら在庫の少ない箱を選ぶ（箱単位の在庫課金を小さくする）
  3. 一度触れた箱からは追加で取り出してもコストが増えない（在庫課金は箱ごとに1回）

ほど安くなる。あたり率（出庫枚数 / 触れた箱の在庫総数）も同時に上がる。

これを貪欲な重み付き集合被覆として解く:
その日に必要なカードを最も安く供給できる箱（限界コスト / 新規にカバーできる需要 が
最小の箱）を1つずつ確定し、確定した箱からはカバーできる需要をすべて取り切る。
"""
from collections import defaultdict

from sim.algorithms.base import OutboundAlgorithm
from sim.models import Order, StorageState


class ConsolidatedStorageOutbound(OutboundAlgorithm):
    """需要を少数・低在庫の箱に寄せて出庫する貪欲アルゴリズム。

    Args:
        pick_per_storage_sec: 箱を1つ触れるごとの固定コスト（コスト推定用）。
        per_card_sec: 箱の在庫1枚あたりのコスト（コスト推定用）。

    これらはシナリオの costs と同じ値を渡すと精度が上がるが、相対的な比率が
    保たれていれば貪欲の判断はほぼ変わらない。
    """

    def __init__(
        self,
        pick_per_storage_sec: float = 58.49,
        per_card_sec: float = 0.2,
    ):
        self.pick_per_storage_sec = pick_per_storage_sec
        self.per_card_sec = per_card_sec

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
        # key -> 残り必要数
        demand: dict[tuple[str, str], int] = defaultdict(int)
        # key -> その key を必要とする注文インデックスのリスト
        orders_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
        order_need: list[int] = []
        for idx, o in enumerate(orders):
            key = (o.product_id, o.rank)
            demand[key] += o.quantity
            orders_by_key[key].append(idx)
            order_need.append(o.quantity)

        # 注文への割り当て時に走査位置を進めるためのポインタ
        order_ptr: dict[tuple[str, str], int] = defaultdict(int)

        def _next_order_idx(key: tuple[str, str]) -> int | None:
            lst = orders_by_key[key]
            p = order_ptr[key]
            while p < len(lst) and order_need[lst[p]] == 0:
                p += 1
            order_ptr[key] = p
            return lst[p] if p < len(lst) else None

        # ---- 各箱の、需要に一致する取り出し可能カードを集める ----
        # sid -> key -> [card_id, ...]
        avail: dict[str, dict[tuple[str, str], list[str]]] = {}
        # sid -> 箱の在庫総数（課金対象）
        inv: dict[str, int] = {}
        for sid, s in storages.items():
            matched: dict[tuple[str, str], list[str]] = defaultdict(list)
            for c in s.cards:
                key = (c.product_id, c.rank)
                if key in demand:
                    matched[key].append(c.card_id)
            if matched:
                avail[sid] = matched
                inv[sid] = s.count

        touched: set[str] = set()

        def _take_all_coverable(sid: str) -> None:
            """確定した箱から、現在の需要でカバーできるカードをすべて取り出す。"""
            for key, card_ids in avail[sid].items():
                while demand[key] > 0 and card_ids:
                    order_idx = _next_order_idx(key)
                    if order_idx is None:
                        break
                    cid = card_ids.pop()
                    assignments.append((orders[order_idx], cid))
                    order_need[order_idx] -= 1
                    demand[key] -= 1

        # ---- 貪欲ループ: 限界コスト / カバー需要 が最小の箱を1つずつ確定 ----
        while any(v > 0 for v in demand.values()):
            best_sid: str | None = None
            best_ratio = float("inf")
            best_cover = -1
            for sid, matched in avail.items():
                if sid in touched:
                    continue
                cover = 0
                for key, card_ids in matched.items():
                    d = demand[key]
                    if d <= 0:
                        continue
                    cover += min(len(card_ids), d)
                if cover == 0:
                    continue
                cost = self.pick_per_storage_sec + inv[sid] * self.per_card_sec
                ratio = cost / cover
                if (
                    ratio < best_ratio
                    or (ratio == best_ratio and cover > best_cover)
                    or (
                        ratio == best_ratio
                        and cover == best_cover
                        and best_sid is not None
                        and _id_key(sid) < _id_key(best_sid)
                    )
                ):
                    best_ratio = ratio
                    best_cover = cover
                    best_sid = sid

            if best_sid is None:
                # これ以上カバーできる箱がない（在庫不足）。残需要は割り当てない。
                break

            touched.add(best_sid)
            _take_all_coverable(best_sid)

        return assignments
