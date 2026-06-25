"""Flask Web アプリ（ローカル閲覧用）。"""
from __future__ import annotations
import csv
import importlib
import inspect
import json
from pathlib import Path

import yaml
from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)


def _get_data_dir() -> Path:
    return Path(app.config.get("DATA_DIR", "./data"))


def _get_datasets() -> list[str]:
    datasets_dir = _get_data_dir() / "datasets"
    if not datasets_dir.exists():
        return []
    return sorted(p.name for p in datasets_dir.iterdir() if p.is_dir())


def _get_scenarios() -> list[str]:
    scenario_dir = _get_data_dir() / "scenarios"
    if not scenario_dir.exists():
        return []
    return sorted(p.stem for p in scenario_dir.glob("*.yaml"))


def _get_results_for_dataset(dataset: str) -> list[str]:
    """指定データセットで実行済みのシナリオ名リストを返す。"""
    output_dir = _get_data_dir() / "output" / dataset
    if not output_dir.exists():
        return []
    return sorted(p.name for p in output_dir.iterdir() if p.is_dir())


def _get_all_results() -> dict[str, list[str]]:
    """dataset -> [scenario, ...] のマップを返す。"""
    output_dir = _get_data_dir() / "output"
    if not output_dir.exists():
        return {}
    result: dict[str, list[str]] = {}
    for dataset_dir in sorted(output_dir.iterdir()):
        if not dataset_dir.is_dir():
            continue
        scenarios = sorted(p.name for p in dataset_dir.iterdir() if p.is_dir())
        if scenarios:
            result[dataset_dir.name] = scenarios
    return result


def _class_doc(class_path: str) -> str:
    """'module:Class' のクラス docstring を取得する（取得不能なら空文字）。"""
    if not class_path or ":" not in class_path:
        return ""
    module_path, class_name = class_path.split(":", 1)
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return inspect.getdoc(cls) or ""
    except Exception:
        return ""


def _load_scenario_meta(scenario: str) -> dict | None:
    """シナリオ YAML を直接読み、説明文・使用アルゴリズム・引数などを返す。

    アルゴリズムクラスのインポートはせず、表示用のメタ情報のみを抽出する
    （クラスが存在しなくても結果ページが壊れないように）。
    """
    path = _get_data_dir() / "scenarios" / f"{scenario}.yaml"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    def _component(section: str) -> dict:
        s = data.get(section) or {}
        class_path = s.get("class", "") or ""
        short = class_path.split(":")[-1] if class_path else ""
        return {
            "class_path": class_path,
            "class_name": short,
            "args": s.get("args") or {},
            "doc": _class_doc(class_path),
        }

    storages = data.get("storages")
    return {
        "name": data.get("name", scenario),
        "description": (data.get("description") or "").strip(),
        "inbound": _component("inbound"),
        "outbound": _component("outbound"),
        "stocktake": _component("stocktake"),
        "costs": data.get("costs") or {},
        "storages": storages,
    }


def _load_summary(dataset: str, scenario: str) -> list[dict] | None:
    path = _get_data_dir() / "output" / dataset / scenario / "summary.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _summary_stats(dataset: str, scenario: str) -> dict | None:
    """実行済みシナリオの結果サマリ（総工数・あたり率など）を集計して返す。"""
    data = _load_summary(dataset, scenario)
    if not data:
        return None
    total_sec = sum(
        d.get("inbound_cost_sec", 0)
        + d.get("outbound_cost_sec", 0)
        + d.get("stocktake_cost_sec", 0)
        for d in data
    )
    picked = sum(d.get("outbound_cards_count", 0) for d in data)
    touched_inv = sum(d.get("outbound_total_storage_cards", 0) for d in data)
    hit_rate = (picked / touched_inv) if touched_inv else None
    return {
        "total_sec": total_sec,
        "total_hours": total_sec / 3600,
        "outbound_cards": picked,
        "hit_rate": hit_rate,
    }


def _read_csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


# ------------------------------------------------------------------ routes

@app.route("/")
def index():
    datasets = _get_datasets()
    scenarios = _get_scenarios()
    all_results = _get_all_results()
    return render_template(
        "index.html",
        datasets=datasets,
        scenarios=scenarios,
        all_results=all_results,
    )


@app.route("/dataset/<dataset>")
def dataset_detail(dataset: str):
    datasets = _get_datasets()
    if dataset not in datasets:
        abort(404)
    scenarios = _get_scenarios()
    ran_scenarios = _get_results_for_dataset(dataset)
    stats = {s: _summary_stats(dataset, s) for s in ran_scenarios}
    descriptions = {
        s: (_load_scenario_meta(s) or {}).get("description", "") for s in scenarios
    }
    return render_template(
        "dataset.html",
        dataset=dataset,
        scenarios=scenarios,
        ran_scenarios=ran_scenarios,
        stats=stats,
        descriptions=descriptions,
    )


@app.route("/dataset/<dataset>/scenario/<scenario>")
def scenario_detail(dataset: str, scenario: str):
    summary = _load_summary(dataset, scenario)
    if summary is None:
        abort(404)

    output_dir = _get_data_dir() / "output" / dataset / scenario
    detail_headers, detail_rows = _read_csv_rows(output_dir / "daily_detail.csv")
    summary_headers, summary_rows = _read_csv_rows(output_dir / "daily_summary.csv")

    return render_template(
        "scenario.html",
        dataset=dataset,
        scenario_name=scenario,
        summary=summary,
        scenario_meta=_load_scenario_meta(scenario),
        detail_headers=detail_headers,
        detail_rows=detail_rows[:200],
        summary_headers=summary_headers,
        summary_rows=summary_rows,
    )


@app.route("/dataset/<dataset>/scenario/<scenario>/animation")
def scenario_animation(dataset: str, scenario: str):
    path = _get_data_dir() / "output" / dataset / scenario / "animation.json"
    if not path.exists():
        abort(404)
    return render_template(
        "animation.html",
        dataset=dataset,
        scenario_name=scenario,
    )


@app.route("/api/animation/<dataset>/<scenario>")
def api_animation(dataset: str, scenario: str):
    path = _get_data_dir() / "output" / dataset / scenario / "animation.json"
    if not path.exists():
        abort(404)
    with path.open(encoding="utf-8") as f:
        return app.response_class(f.read(), mimetype="application/json")


@app.route("/compare")
def compare():
    dataset = request.args.get("dataset", "")
    datasets = _get_datasets()

    # dataset が未指定なら最初のデータセットをデフォルトに
    if not dataset and datasets:
        dataset = datasets[0]

    ran_scenarios = _get_results_for_dataset(dataset) if dataset else []
    selected = request.args.getlist("s")
    if not selected:
        selected = ran_scenarios[:3]
    else:
        # 存在しないシナリオを除外
        selected = [s for s in selected if s in ran_scenarios]

    summaries: dict[str, list[dict]] = {}
    for name in selected:
        data = _load_summary(dataset, name)
        if data:
            summaries[name] = data

    return render_template(
        "compare.html",
        datasets=datasets,
        current_dataset=dataset,
        ran_scenarios=ran_scenarios,
        selected=selected,
        summaries=summaries,
    )


@app.route("/api/summary/<dataset>/<scenario>")
def api_summary(dataset: str, scenario: str):
    data = _load_summary(dataset, scenario)
    if data is None:
        abort(404)
    return jsonify(data)


@app.route("/dataset/<dataset>/input/<filename>")
def input_view(dataset: str, filename: str):
    allowed = {"inbound.csv", "initial_stock.csv", "storages.csv", "orders.csv"}
    if filename not in allowed:
        abort(404)
    if dataset not in _get_datasets():
        abort(404)
    path = _get_data_dir() / "datasets" / dataset / filename
    headers, rows = _read_csv_rows(path)
    return render_template(
        "csv_view.html",
        title=f"{dataset} / {filename}",
        back_url=f"/dataset/{dataset}",
        headers=headers,
        rows=rows,
    )


def run_app(data_dir: str = "./data", host: str = "127.0.0.1", port: int = 8080, debug: bool = False):
    app.config["DATA_DIR"] = data_dir
    app.run(host=host, port=port, debug=debug)
