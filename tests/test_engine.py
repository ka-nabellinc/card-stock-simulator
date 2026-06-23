"""エンジンのコスト計算とあたり率のテスト。"""
from datetime import date

import pytest

from sim.algorithms.baseline import FillEmptyStorageInbound, NoStocktake, OldestFirstOutbound
from sim.engine import run_simulation
from sim.models import Card, Order, Storage
from sim.scenario import CostConfig, Scenario


def _make_scenario(**cost_kwargs) -> Scenario:
    costs = CostConfig(
        inbound_per_storage_sec=cost_kwargs.get("inbound_per_storage_sec", 30),
        outbound_pick_per_storage_sec=cost_kwargs.get("outbound_pick_per_storage_sec", 60),
        outbound_per_card_sec=cost_kwargs.get("outbound_per_card_sec", 2),
    )
    return Scenario(
        name="test",
        inbound=FillEmptyStorageInbound(),
        outbound=OldestFirstOutbound(),
        stocktake=NoStocktake(),
        costs=costs,
    )


def _make_storages(*args) -> dict[str, Storage]:
    """(storage_id, capacity) のタプルのリストからストレージを生成する。"""
    return {sid: Storage(storage_id=sid, capacity=cap) for sid, cap in args}


class TestInboundCost:
    def test_single_storage(self):
        """1ストレージへの入庫コストは inbound_per_storage_sec × 1。"""
        scenario = _make_scenario(inbound_per_storage_sec=30)
        storages = _make_storages(("S1", 10))
        cards = [
            Card(card_id="C1", product_id="P1", rank="S", arrival_date=date(2024, 1, 1)),
            Card(card_id="C2", product_id="P1", rank="S", arrival_date=date(2024, 1, 1)),
        ]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards={},
            inbound_cards=cards,
            orders=[],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
        )
        assert len(logs) == 1
        assert logs[0].inbound_cost_sec == 30.0

    def test_two_storages(self):
        """2ストレージに分かれて入庫すると inbound_per_storage_sec × 2。"""
        scenario = _make_scenario(inbound_per_storage_sec=30)
        storages = _make_storages(("S1", 1), ("S2", 1))
        cards = [
            Card(card_id="C1", product_id="P1", rank="S", arrival_date=date(2024, 1, 1)),
            Card(card_id="C2", product_id="P1", rank="S", arrival_date=date(2024, 1, 1)),
        ]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards={},
            inbound_cards=cards,
            orders=[],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
        )
        assert logs[0].inbound_cost_sec == 60.0


class TestOutboundCost:
    def test_outbound_cost_formula(self):
        """
        出庫コスト = ストレージ数 × pick_sec + 対象ストレージ内総カード数 × per_card_sec
        ストレージS1に3枚あって1枚出庫する場合:
          1ストレージ × 60秒 + 3枚 × 2秒 = 66秒
        """
        scenario = _make_scenario(
            outbound_pick_per_storage_sec=60,
            outbound_per_card_sec=2,
        )
        storages = _make_storages(("S1", 10))
        initial_cards = {
            "C1": Card("C1", "P1", "S", date(2024, 1, 1), "S1"),
            "C2": Card("C2", "P1", "S", date(2024, 1, 1), "S1"),
            "C3": Card("C3", "P1", "S", date(2024, 1, 1), "S1"),
        }
        storages["S1"].cards = list(initial_cards.values())

        orders = [Order(order_date=date(2024, 1, 2), product_id="P1", rank="S", quantity=1, order_id="O1")]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards=initial_cards,
            inbound_cards=[],
            orders=orders,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
        )
        assert logs[0].outbound_cost_sec == 60 + 3 * 2  # 66秒

    def test_outbound_cost_two_storages(self):
        """
        2ストレージにまたがって出庫する場合:
        S1に2枚、S2に2枚。それぞれ1枚ずつ出庫。
        コスト = 2 × 60 + (2 + 2) × 2 = 128秒
        """
        scenario = _make_scenario(
            outbound_pick_per_storage_sec=60,
            outbound_per_card_sec=2,
        )
        storages = _make_storages(("S1", 10), ("S2", 10))
        s1_cards = {
            "C1": Card("C1", "P1", "S", date(2024, 1, 1), "S1"),
            "C2": Card("C1b", "P2", "S", date(2024, 1, 1), "S1"),
        }
        s2_cards = {
            "C3": Card("C3", "P3", "S", date(2024, 1, 1), "S2"),
            "C4": Card("C4", "P4", "S", date(2024, 1, 1), "S2"),
        }
        storages["S1"].cards = [s1_cards["C1"], s1_cards["C2"]]
        storages["S2"].cards = [s2_cards["C3"], s2_cards["C4"]]
        all_cards = {**s1_cards, **s2_cards}

        orders = [
            Order(order_date=date(2024, 1, 2), product_id="P1", rank="S", quantity=1, order_id="O1"),
            Order(order_date=date(2024, 1, 2), product_id="P3", rank="S", quantity=1, order_id="O2"),
        ]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards=all_cards,
            inbound_cards=[],
            orders=orders,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
        )
        assert logs[0].outbound_cost_sec == 2 * 60 + 4 * 2  # 128秒


class TestHitRate:
    def test_hit_rate_calculation(self):
        """
        あたり率 = 出庫カード枚数 / 対象ストレージ内総カード数
        S1に5枚あって3枚出庫 → あたり率 = 3/5 = 0.6
        """
        scenario = _make_scenario()
        storages = _make_storages(("S1", 10))
        cards = {
            f"C{i}": Card(f"C{i}", "P1", "S", date(2024, 1, 1), "S1")
            for i in range(1, 6)
        }
        storages["S1"].cards = list(cards.values())

        orders = [Order(order_date=date(2024, 1, 2), product_id="P1", rank="S", quantity=3, order_id="O1")]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards=cards,
            inbound_cards=[],
            orders=orders,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
        )
        assert logs[0].hit_rate == pytest.approx(3 / 5)

    def test_no_outbound_no_hit_rate(self):
        """出庫がない日はあたり率なし（None）。"""
        scenario = _make_scenario()
        storages = _make_storages(("S1", 10))
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards={},
            inbound_cards=[],
            orders=[],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
        )
        assert logs[0].hit_rate is None


class TestValidation:
    def test_capacity_exceeded_raises(self):
        """容量超過の入庫はエラーになる。"""
        scenario = _make_scenario()
        storages = _make_storages(("S1", 1))
        cards = [
            Card("C1", "P1", "S", date(2024, 1, 1)),
            Card("C2", "P1", "S", date(2024, 1, 1)),
        ]
        with pytest.raises((RuntimeError, ValueError)):
            run_simulation(
                scenario=scenario,
                storages=storages,
                all_cards={},
                inbound_cards=cards,
                orders=[],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
            )

    def test_product_rank_mismatch_raises(self):
        """商品ID・ランクが一致しないカードの出庫はエラーになる。"""
        from sim.algorithms.base import OutboundAlgorithm
        from sim.models import CardInfo, Order, StorageState

        class BadOutbound(OutboundAlgorithm):
            def select(self, orders, storages):
                all_cards = [c for s in storages.values() for c in s.cards]
                return [(orders[0], all_cards[0].card_id)]

        scenario = Scenario(
            name="bad",
            inbound=FillEmptyStorageInbound(),
            outbound=BadOutbound(),
            stocktake=NoStocktake(),
            costs=CostConfig(30, 60, 2),
        )
        storages = _make_storages(("S1", 10))
        cards = {"C1": Card("C1", "P1", "S", date(2024, 1, 1), "S1")}
        storages["S1"].cards = list(cards.values())
        orders = [Order(order_date=date(2024, 1, 2), product_id="P999", rank="A", quantity=1, order_id="O1")]

        with pytest.raises(ValueError, match="一致しません"):
            run_simulation(
                scenario=scenario,
                storages=storages,
                all_cards=cards,
                inbound_cards=[],
                orders=orders,
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 2),
            )


class TestEndToEnd:
    def test_baseline_scenario_runs(self):
        """baseline シナリオが3日間エラーなく動作する。"""
        scenario = _make_scenario()
        storages = _make_storages(("S1", 20), ("S2", 20))
        inbound = [
            Card("C1", "P1", "S", date(2024, 1, 1)),
            Card("C2", "P1", "A", date(2024, 1, 1)),
            Card("C3", "P2", "S", date(2024, 1, 2)),
        ]
        orders = [
            Order(date(2024, 1, 2), "P1", "S", 1, "O1"),
            Order(date(2024, 1, 3), "P2", "S", 1, "O2"),
        ]
        logs = run_simulation(
            scenario=scenario,
            storages=storages,
            all_cards={},
            inbound_cards=inbound,
            orders=orders,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3),
        )
        assert len(logs) == 3
        assert all(log.total_cost_sec >= 0 for log in logs)
