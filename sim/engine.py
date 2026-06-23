"""シミュレーションエンジン。"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta

from sim.models import Card, CardInfo, DailyLog, Order, Storage, StorageState
from sim.scenario import Scenario


def _build_storage_states(storages: dict[str, Storage]) -> dict[str, StorageState]:
    """ストレージの現在状態をアルゴリズムへ渡す不変スナップショットに変換する。"""
    return {
        sid: StorageState(
            storage_id=sid,
            capacity=s.capacity,
            cards=tuple(
                CardInfo(
                    card_id=c.card_id,
                    product_id=c.product_id,
                    rank=c.rank,
                    arrival_date=c.arrival_date,
                )
                for c in s.cards
            ),
        )
        for sid, s in storages.items()
    }


def _card_index(storages: dict[str, Storage]) -> dict[str, tuple[Card, Storage]]:
    """card_id → (Card, Storage) のインデックスを構築する。"""
    idx: dict[str, tuple[Card, Storage]] = {}
    for storage in storages.values():
        for card in storage.cards:
            idx[card.card_id] = (card, storage)
    return idx


def run_simulation(
    scenario: Scenario,
    storages: dict[str, Storage],
    all_cards: dict[str, Card],
    inbound_cards: list[Card],
    orders: list[Order],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[DailyLog]:
    """
    シミュレーションをstart_dateからend_dateまで毎日実行する。

    Returns:
        日次ログのリスト
    """
    # 全カードを card_id で管理
    cards_by_id: dict[str, Card] = dict(all_cards)

    # 入庫待ちカードを日付ごとにグルーピング
    inbound_by_date: dict[date, list[Card]] = defaultdict(list)
    for card in inbound_cards:
        if card.arrival_date:
            inbound_by_date[card.arrival_date].append(card)

    # 注文を日付ごとにグルーピング
    orders_by_date: dict[date, list[Order]] = defaultdict(list)
    for order in orders:
        orders_by_date[order.order_date].append(order)

    # シミュレーション期間の決定
    all_dates: list[date] = []
    for card in inbound_cards:
        if card.arrival_date:
            all_dates.append(card.arrival_date)
    for order in orders:
        all_dates.append(order.order_date)

    if not all_dates and start_date is None:
        raise ValueError("入力データに日付がありません")

    sim_start = start_date or min(all_dates)
    sim_end = end_date or max(all_dates)

    if sim_start > sim_end:
        raise ValueError(f"開始日 {sim_start} が終了日 {sim_end} より後です")

    logs: list[DailyLog] = []
    current = sim_start

    while current <= sim_end:
        log = DailyLog(date=current)

        # ---------- 1. 入庫処理 ----------
        today_inbound = inbound_by_date.get(current, [])
        if today_inbound:
            states = _build_storage_states(storages)
            inbound_info = [
                CardInfo(
                    card_id=c.card_id,
                    product_id=c.product_id,
                    rank=c.rank,
                    arrival_date=c.arrival_date,
                )
                for c in today_inbound
            ]
            assignments = scenario.inbound.assign(inbound_info, states)

            # バリデーション
            assigned_card_ids = {a[0] for a in assignments}
            for card in today_inbound:
                if card.card_id not in assigned_card_ids:
                    raise ValueError(
                        f"[{current}] 入庫アルゴリズムが card_id '{card.card_id}' を割り当てませんでした"
                    )

            inbound_by_card = {c.card_id: c for c in today_inbound}
            assigned_storage_cards: dict[str, list[str]] = defaultdict(list)
            for card_id, storage_id in assignments:
                if card_id not in inbound_by_card:
                    raise ValueError(
                        f"[{current}] 入庫アルゴリズムが未知の card_id '{card_id}' を返しました"
                    )
                if storage_id not in storages:
                    raise ValueError(
                        f"[{current}] 入庫アルゴリズムが未知の storage_id '{storage_id}' を返しました"
                    )
                assigned_storage_cards[storage_id].append(card_id)

            # 容量チェック
            for storage_id, card_ids in assigned_storage_cards.items():
                storage = storages[storage_id]
                if storage.count + len(card_ids) > storage.capacity:
                    raise ValueError(
                        f"[{current}] ストレージ '{storage_id}' の容量超過: "
                        f"現在{storage.count}枚 + 入庫{len(card_ids)}枚 > 上限{storage.capacity}枚"
                    )

            # 実際に格納
            for card_id, storage_id in assignments:
                card = inbound_by_card[card_id]
                card.storage_id = storage_id
                storages[storage_id].cards.append(card)
                cards_by_id[card_id] = card

            log.inbound_assignments = list(assignments)

            # アニメーション用: ストレージ別入庫枚数
            for _card_id, storage_id in assignments:
                log.inbound_by_storage[storage_id] = (
                    log.inbound_by_storage.get(storage_id, 0) + 1
                )

            # 入庫コスト計算
            used_storage_ids = {a[1] for a in assignments}
            log.inbound_cost_sec = (
                len(used_storage_ids) * scenario.costs.inbound_per_storage_sec
            )

        # ---------- 2. 出庫処理 ----------
        today_orders = orders_by_date.get(current, [])
        if today_orders:
            states = _build_storage_states(storages)
            card_idx = _card_index(storages)
            assignments_out = scenario.outbound.select(today_orders, states)

            # バリデーション
            assigned_out: dict[str, Order] = {}
            for order, card_id in assignments_out:
                if card_id in assigned_out:
                    raise ValueError(
                        f"[{current}] 出庫アルゴリズムが card_id '{card_id}' を重複割り当てしました"
                    )
                if card_id not in card_idx:
                    raise ValueError(
                        f"[{current}] 出庫アルゴリズムが在庫にない card_id '{card_id}' を返しました"
                    )
                card, _ = card_idx[card_id]
                if card.product_id != order.product_id or card.rank != order.rank:
                    raise ValueError(
                        f"[{current}] card_id '{card_id}' (product={card.product_id}, rank={card.rank}) は"
                        f" 注文 (product={order.product_id}, rank={order.rank}) と一致しません"
                    )
                assigned_out[card_id] = order

            # ストレージから取り出す
            out_storage_ids = set()
            for order, card_id in assignments_out:
                card, storage = card_idx[card_id]
                out_storage_ids.add(storage.storage_id)
                storage.cards.remove(card)
                card.storage_id = None
                # アニメーション用: ストレージ別出庫枚数
                log.outbound_by_storage[storage.storage_id] = (
                    log.outbound_by_storage.get(storage.storage_id, 0) + 1
                )

            # 出庫コストとあたり率を計算
            # 対象ストレージの割り出し（実際に在庫があったストレージ、出庫前のカード数を使う）
            # ストレージ内にあったカード数は states（出庫前スナップショット）から取得
            total_storage_cards = 0
            for sid in out_storage_ids:
                total_storage_cards += states[sid].count

            log.outbound_assignments = [(o.order_id, cid) for o, cid in assignments_out]
            log.outbound_cards_count = len(assignments_out)
            log.outbound_total_storage_cards = total_storage_cards
            log.hit_rate = (
                log.outbound_cards_count / total_storage_cards
                if total_storage_cards > 0
                else None
            )
            log.outbound_cost_sec = (
                len(out_storage_ids) * scenario.costs.outbound_pick_per_storage_sec
                + total_storage_cards * scenario.costs.outbound_per_card_sec
            )

        # ---------- 3. 棚卸し処理 ----------
        states = _build_storage_states(storages)
        moves, stocktake_cost = scenario.stocktake.execute(current, states)

        if moves:
            card_idx = _card_index(storages)
            move_dest: dict[str, list[str]] = defaultdict(list)

            for card_id, dest_storage_id in moves:
                if card_id not in card_idx:
                    raise ValueError(
                        f"[{current}] 棚卸しアルゴリズムが在庫にない card_id '{card_id}' を返しました"
                    )
                if dest_storage_id not in storages:
                    raise ValueError(
                        f"[{current}] 棚卸しアルゴリズムが未知の storage_id '{dest_storage_id}' を返しました"
                    )
                move_dest[dest_storage_id].append(card_id)

            # 容量チェック（移動前の状態から計算）
            for dest_id, card_ids in move_dest.items():
                storage = storages[dest_id]
                # 移動元から出ていくカードも考慮
                outgoing = sum(
                    1 for cid, did in moves
                    if cid in {c.card_id for c in storage.cards} and did != dest_id
                )
                new_count = storage.count - outgoing + len(card_ids)
                if new_count > storage.capacity:
                    raise ValueError(
                        f"[{current}] 棚卸し後にストレージ '{dest_id}' の容量超過: "
                        f"{new_count} > {storage.capacity}"
                    )

            # 実際に移動
            for card_id, dest_storage_id in moves:
                card, src_storage = card_idx[card_id]
                src_storage.cards.remove(card)
                card.storage_id = dest_storage_id
                storages[dest_storage_id].cards.append(card)

        log.stocktake_moves = list(moves)
        log.stocktake_cost_sec = stocktake_cost

        # アニメーション用: その日の終了時点でのストレージ別在庫数を記録
        log.storage_counts = {sid: s.count for sid, s in storages.items()}

        logs.append(log)
        current += timedelta(days=1)

    return logs
