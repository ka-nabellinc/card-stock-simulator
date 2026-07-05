"""LowInventoryFirstOutbound（在庫の少ない箱を優先する出庫）のテスト。"""
from datetime import date

from sim.algorithms.lowinv import LowInventoryFirstOutbound
from sim.models import CardInfo, Order, StorageState


def _storage(sid: str, cards: list[CardInfo]) -> StorageState:
    return StorageState(storage_id=sid, capacity=1000, cards=tuple(cards))


def _card(cid: str, pid: str, rank: str) -> CardInfo:
    return CardInfo(card_id=cid, product_id=pid, rank=rank, arrival_date=None)


def _order(pid: str, rank: str, qty: int) -> Order:
    return Order(order_date=date(2024, 1, 1), product_id=pid, rank=rank, quantity=qty)


def test_picks_from_lowest_inventory_box():
    """需要を満たせる箱が複数ある場合、在庫総数が最小の箱から取る。"""
    # 箱1: 在庫3枚（うちP1/S 1枚）、箱2: 在庫1枚（P1/S 1枚）
    s1 = _storage("1", [_card("a", "P1", "S"), _card("x", "P9", "A"), _card("y", "P9", "A")])
    s2 = _storage("2", [_card("b", "P1", "S")])

    result = LowInventoryFirstOutbound().select(
        [_order("P1", "S", 1)], {"1": s1, "2": s2}
    )

    assert len(result) == 1
    # 在庫の少ない箱2のカード b が選ばれる（箱1のaではない）
    assert result[0][1] == "b"


def test_covers_full_demand_across_boxes():
    """1箱で足りない需要は、次に在庫の少ない箱を開けて満たす。"""
    # 箱1: 在庫5枚（P1/S 1枚）、箱2: 在庫2枚（P1/S 2枚）、箱3: 在庫8枚（P1/S 2枚）
    s1 = _storage("1", [_card("a", "P1", "S")] + [_card(f"z{i}", "P9", "A") for i in range(4)])
    s2 = _storage("2", [_card("b", "P1", "S"), _card("c", "P1", "S")])
    s3 = _storage("3", [_card("d", "P1", "S"), _card("e", "P1", "S")]
                        + [_card(f"w{i}", "P9", "A") for i in range(6)])

    result = LowInventoryFirstOutbound().select(
        [_order("P1", "S", 3)], {"1": s1, "2": s2, "3": s3}
    )

    picked = {cid for _o, cid in result}
    assert len(result) == 3
    # 在庫最少の箱2(2枚)を使い切り、次に少ない箱1(5枚)から1枚。箱3(8枚)は開けない。
    assert {"b", "c"}.issubset(picked)
    assert "a" in picked
    assert picked.isdisjoint({"d", "e"})


def test_no_orders_returns_empty():
    s1 = _storage("1", [_card("a", "P1", "S")])
    assert LowInventoryFirstOutbound().select([], {"1": s1}) == []
