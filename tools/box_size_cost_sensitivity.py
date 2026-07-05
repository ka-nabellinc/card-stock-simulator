"""箱サイズ × 箱開け固定費(pick_per_storage_sec) の感度分析。

箱開け固定費ごとに、総工数が最小になる箱サイズ(capacity)を探す。
総容量はどの箱サイズでも一定(既定100,000枚)に揃え、箱サイズだけを変える。
出庫は consolidated。各 pick 行で総工数が最小の箱サイズが「その設備条件での最適」。

使い方:
    uv run python -m tools.box_size_cost_sensitivity [dataset] [total_capacity]
    例: uv run python -m tools.box_size_cost_sensitivity 202606
        uv run python -m tools.box_size_cost_sensitivity fullhistory 100000
"""
from __future__ import annotations

import sys
from pathlib import Path

from sim.algorithms.baseline import FillEmptyStorageInbound, NoStocktake
from sim.algorithms.consolidated import ConsolidatedStorageOutbound
from sim.engine import run_simulation
from sim.io.reader import (
    generate_storages,
    load_inbound,
    load_orders,
    place_initial_stock_auto,
)
from sim.scenario import CostConfig, Scenario

CAPS = [100, 200, 300, 500, 1000]
PICKS = [58.49, 30, 12, 3]


def _fresh(ds_dir: Path, count: int, capacity: int):
    """毎回フレッシュな在庫状態をロード（run_simulation は破壊的なため）。"""
    storages = generate_storages(count, capacity)
    stock = ds_dir / "initial_stock.csv"
    cards = place_initial_stock_auto(stock, storages) if stock.exists() else {}
    inbound = load_inbound(ds_dir / "inbound.csv")
    orders = load_orders(ds_dir / "orders.csv")
    return storages, cards, inbound, orders


def run(ds_dir: Path, total_capacity: int, capacity: int, pick: float) -> float:
    count = total_capacity // capacity
    storages, cards, inbound, orders = _fresh(ds_dir, count, capacity)
    scenario = Scenario(
        name="sens",
        inbound=FillEmptyStorageInbound(),
        outbound=ConsolidatedStorageOutbound(pick_per_storage_sec=pick, per_card_sec=0.2),
        stocktake=NoStocktake(),
        costs=CostConfig(
            inbound_per_storage_sec=30,
            outbound_pick_per_storage_sec=pick,
            outbound_per_card_sec=0.2,
        ),
    )
    logs = run_simulation(
        scenario=scenario, storages=storages, all_cards=cards,
        inbound_cards=inbound, orders=orders,
    )
    return sum(l.total_cost_sec for l in logs) / 3600


def main() -> None:
    dataset = sys.argv[1] if len(sys.argv) > 1 else "202606"
    total_capacity = int(sys.argv[2]) if len(sys.argv) > 2 else 100_000
    ds_dir = Path("data/datasets") / dataset
    if not ds_dir.exists():
        print(f"データセットが見つかりません: {ds_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"データセット: {dataset}  総容量: {total_capacity:,}枚  出庫: consolidated")
    header = "pick秒 |" + "".join(f"{c}枚".rjust(11) for c in CAPS) + "  | 最適箱"
    print(header)
    print("-" * len(header))
    for p in PICKS:
        row = {c: run(ds_dir, total_capacity, c, p) for c in CAPS}
        best = min(row, key=row.get)
        cells = "".join(
            (f"*{row[c]:.1f}" if c == best else f"{row[c]:.1f}").rjust(11) for c in CAPS
        )
        print(f"{p:>6} |{cells}  | {best}枚")
    print("\n(* = その pick 行での総工数最小。あたり率は箱サイズのみで決まり pick 不変)")


if __name__ == "__main__":
    main()
