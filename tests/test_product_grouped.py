"""ProductGroupedInbound（商品別集約入庫）のテスト。"""
from datetime import date

from sim.algorithms.product_grouped import ProductGroupedInbound
from sim.models import CardInfo, Storage, StorageState


def _state(sid: str, capacity: int, cards: list[CardInfo]) -> StorageState:
    return StorageState(storage_id=sid, capacity=capacity, cards=tuple(cards))


def _card(cid: str, pid: str, rank: str) -> CardInfo:
    return CardInfo(card_id=cid, product_id=pid, rank=rank, arrival_date=date(2024, 1, 1))


def test_same_product_different_rank_goes_to_home_box():
    """同じ商品なら別ランクでも既存のホーム箱へ入れる。"""
    # 箱1: P1(rank S)のホーム箱、箱2: 空
    s1 = _state("1", 10, [_card("a", "P1", "S")])
    s2 = _state("2", 10, [])

    # P1 の rank A を入庫 → 箱1（P1のホーム）へ
    result = ProductGroupedInbound().assign(
        [_card("b", "P1", "A")], {"1": s1, "2": s2}
    )

    assert result == [("b", "1")]


def test_different_products_open_separate_homes():
    """異なる商品は別のホーム箱（空き箱）に開く。"""
    s1 = _state("1", 10, [_card("a", "P1", "S")])
    s2 = _state("2", 10, [])
    s3 = _state("3", 10, [])

    result = ProductGroupedInbound().assign(
        [_card("b", "P2", "S"), _card("c", "P2", "A")], {"1": s1, "2": s2, "3": s3}
    )

    # P2 の2枚は同じ新規ホーム箱にまとまる（P1の箱1は避ける）
    dests = {cid: sid for cid, sid in result}
    assert dests["b"] == dests["c"]
    assert dests["b"] != "1"


def test_all_cards_assigned():
    """全カードが割り当てられる。"""
    s1 = _state("1", 5, [])
    s2 = _state("2", 5, [])
    cards = [_card(f"c{i}", f"P{i % 3}", "S") for i in range(6)]

    result = ProductGroupedInbound().assign(cards, {"1": s1, "2": s2})

    assert {cid for cid, _ in result} == {c.card_id for c in cards}
