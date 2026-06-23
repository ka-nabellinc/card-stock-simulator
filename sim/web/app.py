"""Flask Web アプリ（ローカル閲覧用）。"""
from __future__ import annotations
import csv
import json
from pathlib import Path

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


def _load_summary(dataset: str, scenario: str) -> list[dict] | None:
    path = _get_data_dir() / "output" / dataset / scenario / "summary.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


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
    return render_template(
        "dataset.html",
        dataset=dataset,
        scenarios=scenarios,
        ran_scenarios=ran_scenarios,
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
        summaries_json=json.dumps(summaries),
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
