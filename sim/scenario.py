"""シナリオ YAML のロードとアルゴリズムの動的インポート。"""
from __future__ import annotations
import importlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from sim.algorithms.base import InboundAlgorithm, OutboundAlgorithm, StocktakeAlgorithm


@dataclass
class CostConfig:
    inbound_per_storage_sec: float
    outbound_pick_per_storage_sec: float
    outbound_per_card_sec: float


@dataclass
class Scenario:
    name: str
    inbound: InboundAlgorithm
    outbound: OutboundAlgorithm
    stocktake: StocktakeAlgorithm
    costs: CostConfig


def _load_class(class_path: str, args: dict):
    """'module.path:ClassName' 形式でクラスを動的ロードしてインスタンス化する。"""
    module_path, class_name = class_path.split(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**(args or {}))


def load_scenario(yaml_path: Path) -> Scenario:
    """YAMLファイルからシナリオを読み込む。"""
    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    name = data.get("name", yaml_path.stem)

    inbound = _load_class(data["inbound"]["class"], data["inbound"].get("args", {}))
    outbound = _load_class(data["outbound"]["class"], data["outbound"].get("args", {}))
    stocktake = _load_class(data["stocktake"]["class"], data["stocktake"].get("args", {}))

    costs_raw = data.get("costs", {})
    costs = CostConfig(
        inbound_per_storage_sec=float(costs_raw.get("inbound_per_storage_sec", 30)),
        outbound_pick_per_storage_sec=float(costs_raw.get("outbound_pick_per_storage_sec", 60)),
        outbound_per_card_sec=float(costs_raw.get("outbound_per_card_sec", 2)),
    )

    if not isinstance(inbound, InboundAlgorithm):
        raise TypeError(f"{type(inbound)} は InboundAlgorithm を継承していません")
    if not isinstance(outbound, OutboundAlgorithm):
        raise TypeError(f"{type(outbound)} は OutboundAlgorithm を継承していません")
    if not isinstance(stocktake, StocktakeAlgorithm):
        raise TypeError(f"{type(stocktake)} は StocktakeAlgorithm を継承していません")

    return Scenario(
        name=name,
        inbound=inbound,
        outbound=outbound,
        stocktake=stocktake,
        costs=costs,
    )
