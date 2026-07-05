"""LatestFirstOutbound（LIFO / FILO: 最新の入庫から出庫）のテスト。"""
from datetime import date

from sim.algorithms.baseline import LatestFirstOutbound, OldestFirstOutbound
from sim.models import CardInfo, Order, StorageState


def _state(sid: str, cards: list[CardInfo]) -> StorageState:
    return StorageState(storage_id=sid, capacity=100, cards=tuple(cards))


def _card(cid: str, pid: str, rank: str, day: int | None) -> CardInfo:
    arrival = date(2024, 1, day) if day is not None else None
    return CardInfo(card_id=cid, product_id=pid, rank=rank, arrival_date=arrival)


def _order(pid: str, rank: str, qty: int) -> Order:
    return Order(order_date=date(2024, 2, 1), product_id=pid, rank=rank, quantity=qty)


def test_picks_newest_first():
    """入庫日が新しいカードから出庫する（LIFO）。"""
    cards = [
        _card("old", "P1", "S", 1),   # 1/1 入庫（古い）
        _card("mid", "P1", "S", 10),  # 1/10 入庫
        _card("new", "P1", "S", 20),  # 1/20 入庫（新しい）
    ]
    result = LatestFirstOutbound().select([_order("P1", "S", 1)], {"1": _state("1", cards)})

    assert len(result) == 1
    assert result[0][1] == "new"


def test_is_reverse_of_fifo():
    """同じ在庫で FIFO と LIFO は逆順に選ぶ。"""
    cards = [
        _card("d1", "P1", "S", 1),
        _card("d2", "P1", "S", 5),
        _card("d3", "P1", "S", 9),
    ]
    storages = {"1": _state("1", cards)}

    lifo = [cid for _o, cid in LatestFirstOutbound().select([_order("P1", "S", 2)], storages)]
    fifo = [cid for _o, cid in OldestFirstOutbound().select([_order("P1", "S", 2)], storages)]

    assert lifo == ["d3", "d2"]  # 新しい順
    assert fifo == ["d1", "d2"]  # 古い順


def test_no_arrival_date_is_treated_as_oldest():
    """入庫日を持たない初期在庫は最古扱い（最後に出庫）。"""
    cards = [
        _card("initial", "P1", "S", None),  # 初期在庫
        _card("dated", "P1", "S", 3),       # 1/3 入庫
    ]
    result = LatestFirstOutbound().select([_order("P1", "S", 1)], {"1": _state("1", cards)})

    # 日付ありの dated が先に出る（initial は最古扱い）
    assert result[0][1] == "dated"
