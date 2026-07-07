# yg データセット（遊戯王 売買履歴）

遊戯王カードの約6ヶ月分（2026-01-01〜2026-07-03, 184 稼働日）の実売買履歴から生成した
データセット。元データ（TSV 3種）はプライベートなため本リポジトリには含めず、生成スクリプト
`build.py` と生成済み CSV のみを収録する。

## 元データ

| ファイル | 役割 | 主なカラム |
|---|---|---|
| `1_card_stock.tsv` | 在庫情報（現在=期間末スナップショット） | `商品ID, SA在庫数, B在庫数, C在庫数, D在庫数, 公開状態, 削除状態` |
| `2_stock_log_sell.tsv` | 注文情報（売上ログ） | `process, card_id, selling_order_id, count, regist_date` |
| `3_stock_log_other.tsv` | 入荷情報（買取・在庫調整ログ） | `process, card_id, buying_order_id, count, regist_date` |

## モデリング方針

- **ID**: ログの `card_id` は `1_card_stock.tsv` の `商品ID` と同一の ID 空間（両ログの
  `card_id` はすべて `商品ID` 集合に含まれる）。個体IDではなく商品(図柄)IDなので、
  シミュレータの `product_id` として扱う。個々のカード個体 (`card_id`) は生成時に採番する
  （初期在庫=`I…`, 入庫=`B…`）。
- **rank**: 取引ログにランク情報が無いため単一ランク `-` に集約する。`1_card_stock.tsv` は
  ランク別在庫を持つが、入荷・注文ログがランク非依存のため、初期在庫・入荷・注文で
  ランクを一致させる必要があり、単一ランクが唯一整合する選択。実質 `product_id` が突合キー。
- **注文** (`orders.csv`): `2_stock_log_sell.tsv` の `process==1`（売上, `count<0`）のみ。
  `quantity = -count`。同一 (日付, 商品) は集約。返品等の他 process は除外。
- **入荷** (`inbound.csv`): `3_stock_log_other.tsv` の `process==2`（在庫化確定, `count>0`）のみ。
  process 2 と 6 は同一買取の別ステージで (card_id, buying_order_id) が約90%重複するため、
  二重計上を避け在庫化確定側の process 2 を採用。`count` 枚を1枚1行に展開。
- **初期在庫** (`initial_stock.csv`): 期間末残高がスナップショットに一致するよう逆算する。
  `initial(P) = max(0, current(P) - inbound_total(P) + order_total(P))`。
  ID 昇順の箱へ順詰めする。

## 規模

| 項目 | 値 |
|---|---|
| 商品数 (product_id) | 54,523 |
| 初期在庫 | 962,579 枚 |
| 入荷 | 949,418 枚 |
| 注文 | 551,117 行（1,177,351 枚） |
| ストレージ | 1,205 箱 × 1,000 枚（在庫ピーク 963,275 × 1.25 で確保）|

## 再生成

元データを `~/Downloads/` に置いた状態で:

```bash
uv run python data/datasets/yg/build.py
```
