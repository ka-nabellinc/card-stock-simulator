"""
できるだけ「ばらける」ように入庫するアルゴリズム（エントロピー最大化）。

GroupByProductInbound の真逆。同じ (product_id, rank) を可能な限り別々の箱へ分散し、
各箱に入る商品の多様性（=エントロピー）が高くなるよう配置する。consolidated 出庫と
組み合わせて、「集約」「中立」「分散」の3水準を比較する実験用。

直感的には最悪手になるはず:
  - 入庫: 1枚ごとに別の箱へ散らすため、1日に触れる箱数が激増 → 入庫コスト増大。
  - 出庫: ある商品の在庫が全箱に薄く散るため、注文を満たすのに多数の箱を触る
          必要が出て、あたり率は下がり出庫コストも増える。
"""
from collections import defaultdict

from sim.algorithms.base import InboundAlgorithm
from sim.models import CardInfo, StorageState


class ScatterInbound(InboundAlgorithm):
    """同じ商品・ランクをできるだけ別々の箱へ分散して入庫する。

    各カードの配置先は、空きのある箱の中から次の優先順で選ぶ:
      1. その (product_id, rank) を含む枚数が最も少ない箱
      2. （同数なら）最も空いている箱（在庫を平準化し全体のエントロピーを上げる）
      3. （同じなら）ID 昇順
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
        # 各箱が含む key ごとの枚数
        key_count: dict[str, dict[tuple[str, str], int]] = {
            sid: defaultdict(int) for sid in storages
        }
        for sid, s in storages.items():
            for c in s.cards:
                key_count[sid][(c.product_id, c.rank)] += 1

        # 決定的なタイブレークのため ID 昇順で走査する
        box_ids = sorted(storages.keys(), key=_id_key)

        for card in cards:
            key = (card.product_id, card.rank)
            best_sid: str | None = None
            best_tuple: tuple[int, int] | None = None
            for sid in box_ids:
                if avail[sid] <= 0:
                    continue
                kc = key_count[sid].get(key, 0)
                # その key が少ない箱を優先、同数なら空きが大きい箱（=より分散）
                t = (kc, -avail[sid])
                if best_tuple is None or t < best_tuple:
                    best_tuple = t
                    best_sid = sid

            if best_sid is None:
                raise RuntimeError(
                    "入庫できないカードがあります: 空き容量が不足しています"
                )

            assignments.append((card.card_id, best_sid))
            avail[best_sid] -= 1
            key_count[best_sid][key] += 1

        return assignments
