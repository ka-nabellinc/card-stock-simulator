"""シミュレーション結果の出力。"""
from __future__ import annotations
import csv
import json
from pathlib import Path

from sim.models import DailyLog


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def write_daily_logs(logs: list[DailyLog], output_dir: Path) -> None:
    """日次作業明細を CSV に保存する。"""
    path = output_dir / "daily_detail.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date", "type", "card_id", "storage_id",
        ])
        for log in logs:
            for card_id, storage_id in log.inbound_assignments:
                writer.writerow([log.date.isoformat(), "inbound", card_id, storage_id])
            for order, card_id in log.outbound_assignments:
                writer.writerow([log.date.isoformat(), "outbound", card_id, ""])
            for card_id, storage_id in log.stocktake_moves:
                writer.writerow([log.date.isoformat(), "stocktake", card_id, storage_id])


def write_daily_summary(logs: list[DailyLog], output_dir: Path) -> None:
    """日次サマリを CSV に保存する。"""
    path = output_dir / "daily_summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date",
            "inbound_cost_sec",
            "outbound_cost_sec",
            "stocktake_cost_sec",
            "total_cost_sec",
            "hit_rate",
            "inbound_count",
            "outbound_count",
        ])
        for log in logs:
            writer.writerow([
                log.date.isoformat(),
                round(log.inbound_cost_sec, 2),
                round(log.outbound_cost_sec, 2),
                round(log.stocktake_cost_sec, 2),
                round(log.total_cost_sec, 2),
                round(log.hit_rate, 4) if log.hit_rate is not None else "",
                len(log.inbound_assignments),
                len(log.outbound_assignments),
            ])


def write_summary_json(logs: list[DailyLog], output_dir: Path) -> None:
    """グラフ用のJSONサマリを保存する。"""
    data = []
    for log in logs:
        data.append({
            "date": log.date.isoformat(),
            "inbound_cost_sec": round(log.inbound_cost_sec, 2),
            "outbound_cost_sec": round(log.outbound_cost_sec, 2),
            "stocktake_cost_sec": round(log.stocktake_cost_sec, 2),
            "total_cost_sec": round(log.total_cost_sec, 2),
            "hit_rate": round(log.hit_rate, 4) if log.hit_rate is not None else None,
            "inbound_count": len(log.inbound_assignments),
            "outbound_count": len(log.outbound_assignments),
            "outbound_cards_count": log.outbound_cards_count,
            "outbound_total_storage_cards": log.outbound_total_storage_cards,
        })
    path = output_dir / "summary.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_animation_json(
    logs: list[DailyLog], storage_capacity: dict[str, int], output_dir: Path
) -> None:
    """アニメーション用のストレージ別在庫推移を保存する。

    storage_ids に並んだ順で、各フレーム（=1日）の在庫数・入庫数・出庫数を
    配列で持つ。Web 側はこの配列を使って倉庫マップを描画する。
    """
    def _key(sid: str):
        return (0, int(sid)) if sid.isdigit() else (1, sid)

    storage_ids = sorted(storage_capacity.keys(), key=_key)
    capacity = [storage_capacity[sid] for sid in storage_ids]

    frames = []
    for log in logs:
        frames.append({
            "date": log.date.isoformat(),
            "counts": [log.storage_counts.get(sid, 0) for sid in storage_ids],
            "inbound": [log.inbound_by_storage.get(sid, 0) for sid in storage_ids],
            "outbound": [log.outbound_by_storage.get(sid, 0) for sid in storage_ids],
            "inbound_total": sum(log.inbound_by_storage.values()),
            "outbound_total": sum(log.outbound_by_storage.values()),
        })

    data = {
        "storage_ids": storage_ids,
        "capacity": capacity,
        "frames": frames,
    }
    path = output_dir / "animation.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def write_all(
    logs: list[DailyLog],
    output_dir: Path,
    storage_capacity: dict[str, int] | None = None,
) -> None:
    ensure_output_dir(output_dir)
    write_daily_logs(logs, output_dir)
    write_daily_summary(logs, output_dir)
    write_summary_json(logs, output_dir)
    if storage_capacity is not None:
        write_animation_json(logs, storage_capacity, output_dir)
