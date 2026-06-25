"""CSV入力データの読み込み。"""
from __future__ import annotations
import csv
from datetime import date, datetime
from pathlib import Path

from sim.models import Card, Order, Storage


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def load_storages(path: Path) -> dict[str, Storage]:
    """storages.csv を読み込む。"""
    storages: dict[str, Storage] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            storage_id = row["storage_id"].strip()
            capacity = int(row["capacity"].strip())
            storages[storage_id] = Storage(storage_id=storage_id, capacity=capacity)
    return storages


def generate_storages(count: int, capacity: int) -> dict[str, Storage]:
    """ID '1'..'count'、各容量 capacity のストレージを生成する。"""
    if count <= 0 or capacity <= 0:
        raise ValueError(f"count と capacity は正の整数で指定してください (count={count}, capacity={capacity})")
    return {
        str(i): Storage(storage_id=str(i), capacity=capacity)
        for i in range(1, count + 1)
    }


def load_initial_stock(path: Path, storages: dict[str, Storage]) -> dict[str, Card]:
    """initial_stock.csv を読み込んでカードをストレージへ配置する。"""
    cards: dict[str, Card] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_id = row["card_id"].strip()
            product_id = row["product_id"].strip()
            rank = row["rank"].strip()
            storage_id = row["storage_id"].strip()

            if storage_id not in storages:
                raise ValueError(f"initial_stock: 存在しないストレージID '{storage_id}' (card_id={card_id})")
            if card_id in cards:
                raise ValueError(f"initial_stock: カードID重複 '{card_id}'")

            card = Card(
                card_id=card_id,
                product_id=product_id,
                rank=rank,
                arrival_date=None,
                storage_id=storage_id,
            )
            storage = storages[storage_id]
            if len(storage.cards) >= storage.capacity:
                raise ValueError(
                    f"initial_stock: ストレージ '{storage_id}' の容量 ({storage.capacity}) を超えています"
                )
            storage.cards.append(card)
            cards[card_id] = card

    return cards


def place_initial_stock_auto(path: Path, storages: dict[str, Storage]) -> dict[str, Card]:
    """initial_stock.csv の storage_id を無視し、新しいストレージ群へ順に詰める。

    シナリオがストレージ定義を上書きした場合、CSV に書かれた元の storage_id は
    無効になる（箱数・容量が変わるため）。ここでは初期在庫を ID 昇順の箱へ容量の
    許す限り順番に格納する。あくまで開始時点の在庫配置であり、以降はアルゴリズムが
    入出庫を担う。
    """
    def _id_key(sid: str):
        return (0, int(sid)) if sid.isdigit() else (1, sid)

    ordered = sorted(storages.values(), key=lambda s: _id_key(s.storage_id))
    cards: dict[str, Card] = {}
    si = 0
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_id = row["card_id"].strip()
            if card_id in cards:
                raise ValueError(f"initial_stock: カードID重複 '{card_id}'")
            # 空きのある箱まで進める
            while si < len(ordered) and len(ordered[si].cards) >= ordered[si].capacity:
                si += 1
            if si >= len(ordered):
                raise ValueError(
                    "initial_stock: 初期在庫を収めるストレージ容量が不足しています"
                )
            storage = ordered[si]
            card = Card(
                card_id=card_id,
                product_id=row["product_id"].strip(),
                rank=row["rank"].strip(),
                arrival_date=None,
                storage_id=storage.storage_id,
            )
            storage.cards.append(card)
            cards[card_id] = card
    return cards


def load_inbound(path: Path) -> list[Card]:
    """inbound.csv を読み込む。"""
    cards: list[Card] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_id = row["card_id"].strip()
            if card_id in seen_ids:
                raise ValueError(f"inbound: カードID重複 '{card_id}'")
            seen_ids.add(card_id)
            cards.append(Card(
                card_id=card_id,
                product_id=row["product_id"].strip(),
                rank=row["rank"].strip(),
                arrival_date=_parse_date(row["arrival_date"]),
            ))
    return cards


def load_orders(path: Path) -> list[Order]:
    """orders.csv を読み込む。"""
    orders: list[Order] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            orders.append(Order(
                order_date=_parse_date(row["order_date"]),
                product_id=row["product_id"].strip(),
                rank=row["rank"].strip(),
                quantity=int(row["quantity"].strip()),
                order_id=f"order-{i+1:04d}",
            ))
    return orders
