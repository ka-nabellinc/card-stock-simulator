# アーキテクチャ設計

## ディレクトリ構成

```
card-stock-simulator/
├── pyproject.toml          # uv プロジェクト定義
├── README.md
├── ARCHITECTURE.md
├── data/
│   ├── datasets/           # 入力データセット（複数可）
│   │   └── {dataset_name}/
│   │       ├── storages.csv
│   │       ├── initial_stock.csv   # 任意
│   │       ├── inbound.csv
│   │       └── orders.csv
│   ├── scenarios/          # シナリオ YAML（データセットに依存しない）
│   │   ├── baseline.yaml
│   │   └── simple.yaml
│   └── output/             # データセット × シナリオ別出力
│       └── {dataset_name}/
│           └── {scenario_name}/
│               ├── daily_detail.csv
│               ├── daily_summary.csv
│               └── summary.json
├── sim/
│   ├── models.py           # データモデル
│   ├── scenario.py         # シナリオロード
│   ├── engine.py           # シミュレーションエンジン
│   ├── run.py              # CLI エントリーポイント
│   ├── web_run.py          # Web アプリ起動スクリプト
│   ├── algorithms/
│   │   ├── base.py         # ABC 定義
│   │   └── baseline.py     # baseline 実装
│   ├── io/
│   │   ├── reader.py       # CSV 読み込み
│   │   └── writer.py       # 結果出力
│   └── web/
│       ├── app.py          # Flask アプリ
│       └── templates/      # Jinja2 テンプレート
└── tests/
    └── test_engine.py
```

---

## モジュール責務

### `sim/models.py`

ドメインオブジェクトを定義します。

- **`Card`**: カード個体。`card_id`（個体ID）、`product_id`（商品ID/図柄）、`rank`（状態）、`arrival_date`、`storage_id` を持つ。エンジン内部で可変。
- **`Storage`**: ストレージ（箱）。`storage_id`、`capacity`、`cards`（Card のリスト）を持つ。エンジン内部で可変。
- **`CardInfo`**: `frozen=True` の不変スナップショット。アルゴリズムへ渡す。
- **`StorageState`**: `frozen=True` の不変スナップショット。アルゴリズムへ渡す。アルゴリズムは状態を直接変更できない。
- **`Order`**: 注文。`order_date`、`product_id`、`rank`、`quantity`、`order_id`。
- **`DailyLog`**: 1日の作業記録。コスト・あたり率・各種明細を格納。

### `sim/algorithms/base.py`

3種のアルゴリズムの抽象基底クラス（ABC）を定義します。

- **`InboundAlgorithm.assign(cards, storages)`**: カードをストレージに割り当てる。
- **`OutboundAlgorithm.select(orders, storages)`**: 注文に対してカードを選択する。
- **`StocktakeAlgorithm.execute(date, storages)`**: 棚卸しを実行する。

すべてのアルゴリズムは `StorageState`（読み取り専用）を参照し、直接在庫を変更しない。在庫更新はエンジンが戻り値に基づいて行う。

### `sim/algorithms/baseline.py`

動作確認用の baseline 実装。

- **`FillEmptyStorageInbound`**: その日の入庫が丸ごと入る箱があれば空きが最小の箱（ぴったり収まる箱）にまとめ、入らなければ空きの大きい箱から順に詰めて触れる箱数を最小化する。
- **`OldestFirstOutbound`**: FIFO（入庫日昇順）で出庫候補を選択。
- **`SmallestStorageFirstOutbound`**: ストレージIDが小さい順に出庫候補を選択。
- **`NoStocktake`**: 何もしない。常に `([], 0.0)` を返す。

同梱シナリオ（`data/scenarios/`）:
- `baseline`: `FillEmptyStorageInbound` + `OldestFirstOutbound` + `NoStocktake`
- `simple`: `FillEmptyStorageInbound` + `SmallestStorageFirstOutbound` + `NoStocktake`

### `sim/scenario.py`

YAML からシナリオを読み込み、アルゴリズムクラスを動的インポートしてインスタンス化する。

クラスパスの形式は `"モジュールパス:クラス名"`（例: `"sim.algorithms.baseline:FillEmptyStorageInbound"`）。

### `sim/engine.py`

シミュレーションのコアロジック。

毎日の処理フロー:
1. **入庫**: `inbound.assign()` を呼び、戻り値を検証してストレージへ格納。コストを計算。
2. **出庫**: `outbound.select()` を呼び、戻り値を検証してストレージから取り出す。コストとあたり率を計算。
3. **棚卸し**: `stocktake.execute()` を呼び、移動を検証・実行。

バリデーション:
- 容量超過の入庫・棚卸し移動 → `ValueError`
- 存在しないカードIDの指定 → `ValueError`
- 商品ID・ランクが注文と一致しないカードの出庫 → `ValueError`
- 同一カードの重複割り当て → `ValueError`
- 入庫アルゴリズムがカードを割り当てなかった → `ValueError`

### `sim/io/reader.py`

CSV 入力を読み込み、`Storage` / `Card` / `Order` オブジェクトに変換する。重複カードID・存在しないストレージIDなどを早期に検出する。

### `sim/io/writer.py`

シミュレーション結果を3種のファイルに出力する。

- `daily_detail.csv`: 入庫・出庫・棚卸しの行レベル明細
- `daily_summary.csv`: 日次集計（コスト内訳・あたり率）
- `summary.json`: グラフ用（Web アプリが参照）
- `animation.json`: 在庫変動アニメーション用（`storage_ids` と日次フレームの在庫数・入庫数・出庫数を配列で保持）

### `sim/web/app.py`

Flask ローカル Web アプリ。外部公開しない前提でシンプルに実装。

エンドポイント:
- `GET /` — データセット一覧・シナリオ一覧・実行済み結果一覧
- `GET /dataset/<dataset>` — データセット詳細（入力ファイル・シナリオ実行状況）
- `GET /dataset/<dataset>/scenario/<scenario>` — 日次グラフ・明細テーブル
- `GET /dataset/<dataset>/scenario/<scenario>/animation` — 在庫変動アニメーション
- `GET /compare?dataset=<ds>&s=<sc>` — 同一データセット内でのシナリオ比較
- `GET /dataset/<dataset>/input/<filename>` — 入力 CSV の表示
- `GET /api/summary/<dataset>/<scenario>` — JSON API
- `GET /api/animation/<dataset>/<scenario>` — アニメーション用 JSON API

グラフは外部 CDN を使わず、テンプレート内に埋め込んだ軽量 Canvas 描画ユーティリティ（`SimpleChart`）で実現。

---

## コスト計算の定義

仕様書に準拠した計算式:

```
入庫コスト = 入庫対象となった storage_id の数 × inbound_per_storage_sec

出庫コスト = 出庫対象となった storage_id の数 × outbound_pick_per_storage_sec
           + Σ(各対象ストレージの総カード数) × outbound_per_card_sec
           ※ 取り出す枚数ではなく、ストレージの在庫総数で課金

棚卸しコスト = StocktakeAlgorithm.execute() が返した秒数
```

あたり率:
```
hit_rate = 出庫カード数 / 対象ストレージ内の総カード数（出庫前）
```

---

## 設計上の決定

### アルゴリズムへの状態渡し

アルゴリズムには可変な `Storage` を直接渡さず、`frozen=True` の `StorageState` / `CardInfo` スナップショットを渡す。これにより:
- アルゴリズムが在庫を直接変更できない（副作用なし）
- エンジンが戻り値を検証してから状態を更新できる
- アルゴリズムのテストが容易

### 動的クラスロード

`importlib.import_module` + `getattr` で YAML に書かれたクラスパスを動的解決する。`sim` パッケージ外のモジュールも指定可能。

### 外部 CDN なし

Web アプリはローカル閲覧用のため、Canvas API を直接利用したミニマルな折れ線グラフ実装を採用。依存ゼロで動作する。
