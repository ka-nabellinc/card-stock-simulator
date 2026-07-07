"""需要予測ベースの棚卸し・出庫アルゴリズム。"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from sim.algorithms.base import InboundAlgorithm, OutboundAlgorithm, StocktakeAlgorithm
from sim.models import CardInfo, Order, StorageState


def _load_order_csv(path: str) -> list[tuple[date, str, str, int]]:
    """外部注文CSVを読み込む。戻り値: [(日付, product_id, rank, 枚数), ...]"""
    records: list[tuple[date, str, str, int]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = date.fromisoformat(row["日付"])
            records.append((d, row["商品ID"], row["ランク"], int(row["枚数"])))
    return records


def _load_expansion_map(path: str) -> dict[str, str]:
    """外部注文CSVから product_id → エキスパンションマーク のマッピングを作る。"""
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            mapping[row["商品ID"]] = row["エキスパンションマーク"]
    return mapping


class ExpansionGroupInbound(InboundAlgorithm):
    """同じエキスパンションのカードを同じストレージにまとめる入庫アルゴリズム。

    - 1ストレージあたり最大 max_types 種類（product_id+rank の組み合わせ）まで
    - 同じエキスパンションで空きがある箱があればそこへ入れる
    - なければ新しい箱を開ける
    - エキスパンション不明のカードは通常の FillEmptyStorage と同じ扱い
    """

    def __init__(
        self,
        order_csv: str,
        max_types: int = 10,
        **kwargs,
    ):
        self.expansion_map = _load_expansion_map(order_csv)
        self.max_types = max_types

    def assign(
        self,
        cards: list[CardInfo],
        storages: dict[str, StorageState],
    ) -> list[tuple[str, str]]:
        def _id_key(sid: str):
            return (0, int(sid)) if sid.isdigit() else (1, sid)

        # 既存ストレージのエキスパンション・種類数を把握
        # expansion -> [(storage_id, types_count, available), ...]
        exp_storages: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for sid, storage in storages.items():
            if storage.available == 0:
                continue
            exp_set: set[tuple[str, str]] = set()
            exp_marks: set[str] = set()
            for card in storage.cards:
                exp = self.expansion_map.get(card.product_id, "")
                exp_marks.add(exp)
                exp_set.add((card.product_id, card.rank))
            # 単一エキスパンションのストレージのみ対象（空箱も含む）
            if len(exp_marks) <= 1:
                exp = next(iter(exp_marks)) if exp_marks else ""
                exp_storages[exp].append((sid, len(exp_set), storage.available))

        # エキスパンションごとに空き状況をソート（種類数が多い順→ID順）
        for exp in exp_storages:
            exp_storages[exp].sort(key=lambda x: (-x[1], _id_key(x[0])))

        # 現在の割り当てを追跡（ストレージごとの追加種類と枚数）
        assign_types: dict[str, set[tuple[str, str]]] = defaultdict(set)
        assign_counts: dict[str, int] = defaultdict(int)

        assignments: list[tuple[str, str]] = []

        # 空き箱（エキスパンション未割当）を用意
        empty_storages = sorted(
            [sid for sid, s in storages.items() if s.count == 0 and s.available > 0],
            key=_id_key,
        )
        empty_iter = iter(empty_storages)

        def _find_dest(exp: str, card_type: tuple[str, str]) -> str | None:
            """割り当て先ストレージを探す。なければ空き箱を開ける。"""
            # 同エキスパンションの既存ストレージを探す
            for entry in exp_storages.get(exp, []):
                sid, existing_types, avail = entry
                current_types = assign_types[sid] | {card_type}
                total_types = existing_types + len(assign_types[sid] - {card_type})
                if total_types + (1 if card_type not in assign_types[sid] else 0) <= self.max_types:
                    if avail - assign_counts[sid] > 0:
                        return sid
            # 同エキスパンションの割り当て済み（今回新規）ストレージを探す
            # → assign_types に登録された同エキスパンションの箱
            for sid, types_set in assign_types.items():
                if sid in storages:
                    first_pid = next(iter(types_set))[0] if types_set else None
                    sid_exp = self.expansion_map.get(first_pid, "") if first_pid else exp
                    if sid_exp == exp:
                        total_types_count = len(types_set | {card_type})
                        if total_types_count <= self.max_types:
                            used = assign_counts[sid]
                            cap = storages[sid].available
                            if cap - used > 0:
                                return sid
            # 新しい空き箱を開ける
            try:
                return next(empty_iter)
            except StopIteration:
                return None

        for card in cards:
            exp = self.expansion_map.get(card.product_id, "UNKNOWN")
            card_type = (card.product_id, card.rank)
            dest = _find_dest(exp, card_type)
            if dest is None:
                # 空き箱なし → 空きがある任意のストレージへフォールバック
                dest = next(
                    (sid for sid, s in sorted(storages.items(), key=lambda x: _id_key(x[0]))
                     if s.available - assign_counts[sid] > 0),
                    None,
                )
            if dest is None:
                raise RuntimeError(f"入庫できるストレージがありません: {card.card_id}")
            assignments.append((card.card_id, dest))
            assign_types[dest].add(card_type)
            assign_counts[dest] += 1

        return assignments


class ForecastWeeklyStocktake(StocktakeAlgorithm):
    """需要予測に基づいて売れ筋を1〜10番に集める週次棚卸し。

    - 毎週 weekday（デフォルト: 月曜=0）に実行
    - 当月のデータのみで週次需要を予測（月が変わると自動リセット）
    - 予測数量分を target_storages に集め、外れたカードは末尾ストレージへ退避
    """

    def __init__(
        self,
        order_csv: str,
        target_storages: list[int] | None = None,
        weekday: int = 0,
        capacity_per_type: int = 40,
        move_per_card_sec: float = 30.0,
        **kwargs,
    ):
        self.records = _load_order_csv(order_csv)
        self.target_storage_ids = (
            [str(s) for s in target_storages]
            if target_storages is not None
            else [str(i) for i in range(1, 11)]
        )
        self.target_set = set(self.target_storage_ids)
        self.weekday = weekday
        self.capacity_per_type = capacity_per_type
        self.move_per_card_sec = move_per_card_sec

    def _predict_weekly_demand(
        self, current_date: date
    ) -> dict[tuple[str, str], int]:
        """当月データから (product_id, rank) の週次需要を予測する。"""
        month_start = current_date.replace(day=1)

        # 当月の注文を集計
        monthly: Counter[tuple[str, str]] = Counter()
        weeks_in_month: set[int] = set()
        for d, pid, rank, qty in self.records:
            if d.year == current_date.year and d.month == current_date.month:
                monthly[(pid, rank)] += qty
                # 月内の週番号（月初からの経過週）
                weeks_in_month.add((d - month_start).days // 7)

        if not weeks_in_month:
            return {}

        n_weeks = max(len(weeks_in_month), 1)
        # 週平均を切り上げで予測数量とする
        return {
            key: -(-total // n_weeks)  # 切り上げ除算
            for key, total in monthly.items()
            if total > 0
        }

    def execute(
        self,
        current_date: date,
        storages: dict[str, StorageState],
        order_history: list[tuple[date, Order]] | None = None,
    ) -> tuple[list[tuple[str, str]], float]:
        if current_date.weekday() != self.weekday:
            return [], 0.0

        # 週次需要予測
        demand = self._predict_weekly_demand(current_date)
        if not demand:
            return [], 0.0

        # 予測数量を capacity_per_type で上限クリップ
        forecast: dict[tuple[str, str], int] = {
            k: min(v, self.capacity_per_type) for k, v in demand.items()
        }
        forecast_types = set(forecast.keys())

        # ターゲット内で既に正しく配置されているカードを確認
        already: dict[tuple[str, str], int] = defaultdict(int)
        for sid in self.target_storage_ids:
            if sid not in storages:
                continue
            for card in storages[sid].cards:
                key = (card.product_id, card.rank)
                if key in forecast_types:
                    already[key] += 1

        # 末尾ストレージ（番号が大きい順）を退避先として準備
        outer_sids = sorted(
            [sid for sid in storages if sid not in self.target_set],
            key=lambda s: -int(s) if s.isdigit() else -(10 ** 9),
        )
        outer_free: dict[str, int] = {sid: storages[sid].available for sid in outer_sids}

        # ターゲット内の空き容量を追跡
        target_free: dict[str, int] = {
            sid: storages[sid].available
            for sid in self.target_storage_ids
            if sid in storages
        }

        moves: list[tuple[str, str]] = []

        # ① ターゲット内の「予測外」カードを末尾ストレージへ退避
        for sid in self.target_storage_ids:
            if sid not in storages:
                continue
            for card in storages[sid].cards:
                key = (card.product_id, card.rank)
                if key in forecast_types:
                    continue
                dest = next((s for s in outer_sids if outer_free.get(s, 0) > 0), None)
                if dest is None:
                    break
                moves.append((card.card_id, dest))
                outer_free[dest] -= 1
                target_free[sid] = target_free.get(sid, 0) + 1

        # ② 予測数量に不足しているカードを他ストレージから集める
        # 他ストレージのカード一覧をタイプ別に収集
        other: dict[tuple[str, str], list[str]] = defaultdict(list)
        for sid, storage in storages.items():
            if sid in self.target_set:
                continue
            for card in storage.cards:
                key = (card.product_id, card.rank)
                if key in forecast_types:
                    other[key].append(card.card_id)

        # 需要が多い順に処理
        for key in sorted(forecast_types, key=lambda k: -forecast[k]):
            needed = forecast[key] - already.get(key, 0)
            if needed <= 0:
                continue
            for card_id in other.get(key, []):
                if needed <= 0:
                    break
                dest = next(
                    (sid for sid in self.target_storage_ids if target_free.get(sid, 0) > 0),
                    None,
                )
                if dest is None:
                    break
                moves.append((card_id, dest))
                target_free[dest] -= 1
                needed -= 1

        cost = len(moves) * self.move_per_card_sec
        return moves, cost


class PriorityStorageOutbound(OutboundAlgorithm):
    """優先ストレージ（1〜10番）を先にピックし、足りなければ他から補う出庫。

    優先ストレージ内ではストレージID昇順でカードを選ぶ。
    """

    def __init__(
        self,
        priority_storages: list[int] | None = None,
        **kwargs,
    ):
        self.priority_ids = (
            [str(s) for s in priority_storages]
            if priority_storages is not None
            else [str(i) for i in range(1, 11)]
        )
        self.priority_set = set(self.priority_ids)

    def select(
        self,
        orders: list[Order],
        storages: dict[str, StorageState],
    ) -> list[tuple[Order, str]]:
        def _id_key(sid: str):
            return (0, int(sid)) if sid.isdigit() else (1, sid)

        # 優先ストレージ → その他の順で全カードを並べる
        priority = sorted(
            [s for s in storages.values() if s.storage_id in self.priority_set],
            key=lambda s: _id_key(s.storage_id),
        )
        others = sorted(
            [s for s in storages.values() if s.storage_id not in self.priority_set],
            key=lambda s: _id_key(s.storage_id),
        )

        all_cards: list[tuple[str, CardInfo]] = []
        for storage in priority + others:
            for card in storage.cards:
                all_cards.append((storage.storage_id, card))

        assigned: set[str] = set()
        assignments: list[tuple[Order, str]] = []

        for order in orders:
            needed = order.quantity
            for _sid, card in all_cards:
                if needed <= 0:
                    break
                if card.card_id in assigned:
                    continue
                if card.product_id == order.product_id and card.rank == order.rank:
                    assignments.append((order, card.card_id))
                    assigned.add(card.card_id)
                    needed -= 1

        return assignments
