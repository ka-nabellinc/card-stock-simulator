# card-stock-simulator

トレーディングカード中古流通プラットフォーム向けの倉庫入出庫シミュレーションツールです。
入庫・出庫・棚卸しアルゴリズムを「シナリオ」として差し替えながら、作業工数（秒）とあたり率を比較できます。

---

## Windows 11 環境構築手順（初回のみ）

完全に何もない状態からの手順です。

### 1. Git のインストール

1. https://git-scm.com/download/win を開く
2. **64-bit Git for Windows Setup** をダウンロードしてインストール
3. インストール中の選択肢はすべてデフォルトでOK
4. インストール後、スタートメニューから **Git Bash** を起動して確認：
   ```
   git --version
   ```

### 2. uv のインストール

Git Bash（または PowerShell）で以下を実行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

インストール後、**Git Bash を一度閉じて再度開き**、確認：

```
uv --version
```

### 3. ソースコードの取得

**Git が使える場合：**

```bash
git clone https://github.com/ka-nabellinc/card-stock-simulator.git
cd card-stock-simulator
```

**Git のアクセス権がない場合（ZIP ダウンロード）：**

1. https://github.com/ka-nabellinc/card-stock-simulator を開く
2. 緑色の **Code** ボタンをクリック
3. **Download ZIP** をクリックしてダウンロード
4. ダウンロードした ZIP を右クリック →「すべて展開」で任意のフォルダに解凍
5. Git Bash を起動し、解凍したフォルダに移動：
   ```bash
   cd /c/Users/ユーザー名/Downloads/card-stock-simulator-main
   ```

### 4. 依存パッケージのインストール

```bash
uv sync
```

### 5. Web アプリの起動

```bash
uv run python -m sim.web_run
```

ブラウザで http://127.0.0.1:8080 を開く。

---

## セットアップ（Mac / Linux）

[uv](https://github.com/astral-sh/uv) が必要です。

```bash
cd card-stock-simulator
uv sync
```

---

## サンプル実行（baseline シナリオ × sample データセット）

```bash
uv run python -m sim.run baseline --dataset sample
```

`--dataset` は必須です。`data/datasets/{名前}/` 以下の CSV が読み込まれます。

データルートを変更したい場合:

```bash
uv run python -m sim.run baseline --dataset sample --data-dir ./data
```

期間を明示指定する場合:

```bash
uv run python -m sim.run baseline --dataset sample --start 2024-01-01 --end 2024-01-31
```

実行後、`data/output/{dataset}/{scenario}/` に結果が出力されます。

---

## Web アプリの起動

```bash
uv run python -m sim.web_run
```

ブラウザで http://127.0.0.1:8080/ を開いてください。

オプション:

```bash
uv run python -m sim.web_run --data-dir ./data --port 8080 --debug
```

---

## 同梱アルゴリズム（`sim/algorithms/baseline.py`）

| クラス | 種別 | 動作 |
|---|---|---|
| `FillEmptyStorageInbound` | 入庫 | その日の入庫が丸ごと入る箱（空きが最小の箱を優先）にまとめて入れ、入らなければ空きの大きい箱から順に詰めて触れる箱数を最小化する |
| `OldestFirstOutbound` | 出庫 | 入庫日が古いカードから選ぶ（FIFO） |
| `SmallestStorageFirstOutbound` | 出庫 | ストレージIDが小さい順にカードを選ぶ |
| `ConsolidatedStorageOutbound` | 出庫 | 1日の注文をできるだけ少数・低在庫のストレージにまとめて出庫する（貪欲な重み付き集合被覆）。触れる箱数と箱の在庫課金を減らし、あたり率も上げる |
| `GroupByProductInbound` | 入庫 | 同じ商品・ランクをできるだけ同じ箱（ホーム箱）に寄せて入庫する。あたり率の最適解を検証する用途。実運用では入庫時の仕分け手間が増える |
| `ScatterInbound` | 入庫 | 同じ商品・ランクをできるだけ別々の箱へ分散（エントロピー最大化）して入庫する。集約の真逆を検証する用途 |
| `NoStocktake` | 棚卸し | 何もしない（常に移動なし・コスト0） |

## 同梱シナリオ（`data/scenarios/`）

| シナリオ | 入庫 | 出庫 | 棚卸し |
|---|---|---|---|
| `baseline` | `FillEmptyStorageInbound` | `OldestFirstOutbound` | `NoStocktake` |
| `simple` | `FillEmptyStorageInbound` | `SmallestStorageFirstOutbound` | `NoStocktake` |
| `consolidated` | `FillEmptyStorageInbound` | `ConsolidatedStorageOutbound` | `NoStocktake` |
| `grouped` | `GroupByProductInbound` | `ConsolidatedStorageOutbound` | `NoStocktake` |
| `scattered` | `ScatterInbound` | `ConsolidatedStorageOutbound` | `NoStocktake` |
| `smallbox` | `FillEmptyStorageInbound` | `ConsolidatedStorageOutbound` | `NoStocktake` |
| `box300` | `FillEmptyStorageInbound` | `ConsolidatedStorageOutbound` | `NoStocktake` |

`smallbox`（1箱100枚×1000箱）と `box300`（1箱300枚×334箱）は、`consolidated` と同じアルゴリズムのままストレージ定義だけを上書きして箱サイズの影響を見る実験用シナリオです（後述「ストレージ定義の上書き」）。いずれも総容量を約100,000枚に揃えてあります。

## シナリオの追加方法

### 1. アルゴリズムクラスを実装する

`sim/algorithms/` 以下に新しいモジュールを作成し、以下のいずれかの基底クラスを継承します。

```python
# sim/algorithms/my_algo.py
from sim.algorithms.base import InboundAlgorithm

class SmartInbound(InboundAlgorithm):
    def __init__(self, prefer_empty: bool = True):
        self.prefer_empty = prefer_empty

    def assign(self, cards, storages):
        # storages: dict[str, StorageState]（読み取り専用）
        # return: [(card_id, storage_id), ...]
        ...
```

3種の基底クラス:

| クラス | メソッド | 戻り値 |
|---|---|---|
| `InboundAlgorithm` | `assign(cards, storages)` | `[(card_id, storage_id), ...]` |
| `OutboundAlgorithm` | `select(orders, storages)` | `[(order, card_id), ...]` |
| `StocktakeAlgorithm` | `execute(date, storages)` | `([(card_id, dest_storage_id), ...], cost_sec)` |

### 2. シナリオ YAML を作成する

`data/scenarios/my_scenario.yaml`:

```yaml
name: my_scenario
description: |
  このシナリオの目的や狙いを書く（任意・複数行可）。
  Web のシナリオ結果ページとデータセット一覧に表示される。
inbound:
  class: "sim.algorithms.my_algo:SmartInbound"
  args:
    prefer_empty: true
outbound:
  class: "sim.algorithms.baseline:OldestFirstOutbound"
  args: {}
stocktake:
  class: "sim.algorithms.baseline:NoStocktake"
  args: {}
costs:
  inbound_per_storage_sec: 30
  outbound_pick_per_storage_sec: 60
  outbound_per_card_sec: 2
```

#### ストレージ定義の上書き（任意）

シナリオに `storages` ブロックを追加すると、そのシナリオだけデータセットの
`storages.csv` とは異なる箱構成で実験できます（箱サイズの感度分析など）。

```yaml
# 1箱100枚を1000箱（容量100,000枚）に上書き
storages:
  count: 1000
  capacity: 100
```

または、データセットディレクトリ内の別 CSV を指定:

```yaml
storages:
  file: "storages_small.csv"
```

`storages` を省略するとデータセットの `storages.csv` を使います。上書き時に
`initial_stock.csv` がある場合は、元の `storage_id` を無視して新しい箱へ ID 昇順に
詰め直します（開始時点の在庫配置）。

### 3. 実行する

```bash
uv run python -m sim.run my_scenario --dataset sample
```

---

## テストの実行

```bash
uv run pytest tests/ -v
```

---

## データセットの追加方法

`data/datasets/{データセット名}/` ディレクトリを作成して CSV を配置します。

```
data/datasets/
├── sample/           # サンプル（既存）
│   ├── storages.csv
│   ├── initial_stock.csv
│   ├── inbound.csv
│   └── orders.csv
└── my_dataset/       # 新しいデータセット
    ├── storages.csv
    ├── ...
```

実行:

```bash
uv run python -m sim.run baseline --dataset my_dataset
```

比較は同じデータセット内のシナリオ同士で行います（Web UIの比較ページ）。

## 入力データ形式

`data/datasets/{名前}/` 以下に CSV を配置します。

| ファイル | カラム | 説明 |
|---|---|---|
| `storages.csv` | `storage_id, capacity` | ストレージ定義 |
| `initial_stock.csv` | `product_id, rank, storage_id, card_id` | 初期在庫（任意） |
| `inbound.csv` | `product_id, rank, card_id, arrival_date` | 入庫予定 |
| `orders.csv` | `order_date, product_id, rank, quantity` | 注文 |

---

## 出力データ形式

`data/output/{データセット名}/{シナリオ名}/` に以下が出力されます。

| ファイル | 内容 |
|---|---|
| `daily_detail.csv` | 入庫・出庫・棚卸しの明細（card_id, storage_id, 日付, 種別） |
| `daily_summary.csv` | 日次集計（コスト内訳、あたり率、入出庫枚数） |
| `summary.json` | グラフ用 JSON（Web アプリが参照） |
| `animation.json` | 在庫変動アニメーション用 JSON（日次のストレージ別在庫数・入出庫数） |

Web のシナリオ詳細ページから「在庫変動アニメーション」を開くと、各ストレージの充填率と日々の入出庫を倉庫マップ風に再生できます。
