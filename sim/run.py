"""CLIエントリーポイント。

Usage:
    python -m sim.run <scenario_name> --dataset <dataset_name> [options]
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from pathlib import Path

from sim.engine import run_simulation
from sim.io.reader import (
    generate_storages,
    load_inbound,
    load_initial_stock,
    load_orders,
    load_storages,
    place_initial_stock_auto,
)
from sim.io.writer import write_all
from sim.scenario import load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(
        description="トレーディングカード倉庫シミュレーター"
    )
    parser.add_argument("scenario", help="シナリオ名（scenarios/{name}.yaml）")
    parser.add_argument(
        "--dataset",
        required=True,
        help="データセット名（datasets/{name}/ 以下の CSV を使用）",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="データルートディレクトリ（既定: ./data）",
    )
    parser.add_argument("--start", help="シミュレーション開始日 (YYYY-MM-DD)", default=None)
    parser.add_argument("--end", help="シミュレーション終了日 (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    dataset_dir = data_dir / "datasets" / args.dataset
    scenario_dir = data_dir / "scenarios"
    output_dir = data_dir / "output" / args.dataset / args.scenario

    # データセットディレクトリの存在確認
    if not dataset_dir.exists():
        print(
            f"エラー: データセットディレクトリが見つかりません: {dataset_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # シナリオ読み込み
    scenario_path = scenario_dir / f"{args.scenario}.yaml"
    if not scenario_path.exists():
        print(f"エラー: シナリオファイルが見つかりません: {scenario_path}", file=sys.stderr)
        sys.exit(1)

    print(f"データセット '{args.dataset}' × シナリオ '{args.scenario}'")
    scenario = load_scenario(scenario_path)

    # 入力データ読み込み
    print("入力データを読み込み中...")
    if scenario.storages is not None:
        sc = scenario.storages
        if sc.file:
            storages = load_storages(dataset_dir / sc.file)
            print(f"  ストレージ定義をシナリオで上書き: {sc.file}（{len(storages)} 箱）")
        else:
            storages = generate_storages(sc.count, sc.capacity)
            print(
                f"  ストレージ定義をシナリオで上書き: {sc.count} 箱 × 容量 {sc.capacity}"
            )
    else:
        storages = load_storages(dataset_dir / "storages.csv")

    all_cards = {}
    initial_stock_path = dataset_dir / "initial_stock.csv"
    if initial_stock_path.exists():
        if scenario.storages is not None:
            # ストレージ定義を上書きした場合、元の storage_id は無効なので順に詰め直す
            all_cards = place_initial_stock_auto(initial_stock_path, storages)
        else:
            all_cards = load_initial_stock(initial_stock_path, storages)
        print(f"  初期在庫: {len(all_cards)} 枚")

    inbound_cards = load_inbound(dataset_dir / "inbound.csv")
    print(f"  入庫予定: {len(inbound_cards)} 枚")

    orders = load_orders(dataset_dir / "orders.csv")
    print(f"  注文: {len(orders)} 件")

    start_date = (
        datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    )
    end_date = (
        datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None
    )

    # シミュレーション実行
    print("シミュレーションを実行中...")
    logs = run_simulation(
        scenario=scenario,
        storages=storages,
        all_cards=all_cards,
        inbound_cards=inbound_cards,
        orders=orders,
        start_date=start_date,
        end_date=end_date,
    )

    # 結果出力
    print(f"結果を出力中: {output_dir}")
    storage_capacity = {sid: s.capacity for sid, s in storages.items()}
    write_all(logs, output_dir, storage_capacity=storage_capacity)

    # サマリ表示
    total_cost = sum(log.total_cost_sec for log in logs)
    total_inbound = sum(len(log.inbound_assignments) for log in logs)
    total_outbound = sum(log.outbound_cards_count for log in logs)
    hit_rates = [log.hit_rate for log in logs if log.hit_rate is not None]
    avg_hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else None

    print("\n===== シミュレーション結果 =====")
    print(f"データセット: {args.dataset}")
    print(f"シナリオ: {args.scenario}")
    print(f"期間: {logs[0].date} 〜 {logs[-1].date} ({len(logs)} 日間)")
    print(f"総工数: {total_cost:.1f} 秒 ({total_cost/3600:.2f} 時間)")
    print(f"入庫カード数: {total_inbound} 枚")
    print(f"出庫カード数: {total_outbound} 枚")
    if avg_hit_rate is not None:
        print(f"平均あたり率: {avg_hit_rate:.1%}")
    print("================================")


if __name__ == "__main__":
    main()
