"""YG(遊戯王)売買履歴 → card-stock-simulator データセット生成。

ソース:
  1_card_stock.tsv     在庫情報   商品ID, SA/B/C/D在庫数, 公開状態, 削除状態 (現在=期間末のスナップショット)
  2_stock_log_sell.tsv 注文情報   process, card_id=商品ID, selling_order_id, count(<0=売上), regist_date
  3_stock_log_other.tsv 入荷情報  process, card_id=商品ID, buying_order_id, count(>0=入荷), regist_date

モデリング方針:
  - logs の card_id は file1 の 商品ID と同一空間 → product_id として扱う（個体IDではない）。
  - rank は取引ログに存在しないため単一ランク "-" に集約（product_id が実質キー）。
  - 注文     = file2 process==1 (count<0) の売上のみ。quantity=-count。(date,product)で集約。
  - 入荷     = file3 process==2 (count>0)。process 2 と 6 は同一買取の別ステージ(≈90%重複)
               のため二重計上を避け、在庫化確定に相当する process 2 のみ採用。1枚=1行に展開。
  - 初期在庫 = current(P) - inbound_total(P) + order_total(P) を 0 下限クランプで復元。
               期間末残高が file1 スナップショットにほぼ一致する。1枚=1行に展開し箱へ順詰め。
"""
import csv, collections, os

DL = "/Users/chibiegg/Downloads"
OUT = "/Users/chibiegg/Develop/card-stock-simulator/data/datasets/yg"
RANK = "-"
BOX_CAPACITY = 1000
csv.field_size_limit(10**7)

# ---- 1. 在庫情報 ----
current = collections.Counter()
with open(f"{DL}/1_card_stock.tsv", encoding="utf-8") as f:
    r = csv.reader(f, delimiter="\t"); next(r)
    for row in r:
        current[row[0]] = int(row[1]) + int(row[2]) + int(row[3]) + int(row[4])

# ---- 2. 注文 (file2 process==1, count<0) → (date,pid) 集約 ----
order_agg = collections.Counter()        # (date, pid) -> qty
order_total = collections.Counter()
with open(f"{DL}/2_stock_log_sell.tsv", encoding="utf-8") as f:
    r = csv.reader(f, delimiter="\t"); next(r)
    for row in r:
        if row[1] != "1":
            continue
        cnt = int(row[4])
        if cnt >= 0:
            continue
        d, pid = row[5][:10], row[2]
        order_agg[(d, pid)] += -cnt
        order_total[pid] += -cnt

# ---- 3. 入荷 (file3 process==2, count>0) ----
inbound_events = []                       # (date, pid, cnt)
inbound_total = collections.Counter()
with open(f"{DL}/3_stock_log_other.tsv", encoding="utf-8") as f:
    r = csv.reader(f, delimiter="\t"); next(r)
    for row in r:
        if row[1] != "2":
            continue
        cnt = int(row[4])
        if cnt <= 0:
            continue
        inbound_events.append((row[5][:10], row[2], cnt))
        inbound_total[row[2]] += cnt

# ---- 4. 初期在庫の復元 ----
allpids = set(current) | set(inbound_total) | set(order_total)
initial = {}
for pid in allpids:
    v = current.get(pid, 0) - inbound_total.get(pid, 0) + order_total.get(pid, 0)
    initial[pid] = max(0, v)
init_total = sum(initial.values())

# ---- 5. 在庫ピーク（日中=入荷後・出庫前を含む）で箱数を決定 ----
inbound_by_date = collections.defaultdict(list)
for d, pid, c in inbound_events:
    inbound_by_date[d].append((pid, c))
orders_by_date = collections.defaultdict(list)
for (d, pid), q in order_agg.items():
    orders_by_date[d].append((pid, q))

bal = dict(initial)
total = init_total
peak = init_total                          # 初日開始 = 初期在庫
for d in sorted(set(inbound_by_date) | set(orders_by_date)):
    for pid, c in inbound_by_date.get(d, []):
        bal[pid] = bal.get(pid, 0) + c
        total += c
    if total > peak:                       # 入荷直後（出庫前）のピーク
        peak = total
    for pid, q in orders_by_date.get(d, []):
        take = min(bal.get(pid, 0), q)
        bal[pid] -= take
        total -= take

num_boxes = -(-int(peak * 1.25) // BOX_CAPACITY)   # 25% ヘッドルーム
cap_total = num_boxes * BOX_CAPACITY

# ---- 6. 出力 ----
os.makedirs(OUT, exist_ok=True)

# storages.csv
with open(f"{OUT}/storages.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["storage_id", "capacity"])
    for i in range(1, num_boxes + 1):
        w.writerow([i, BOX_CAPACITY])

# initial_stock.csv : 箱1..N へ順詰め
seq = 0
box_idx = 1
box_fill = 0
with open(f"{OUT}/initial_stock.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["product_id", "rank", "storage_id", "card_id"])
    for pid in sorted(initial):
        for _ in range(initial[pid]):
            if box_fill >= BOX_CAPACITY:
                box_idx += 1; box_fill = 0
            seq += 1
            w.writerow([pid, RANK, box_idx, f"I{seq:07d}"])
            box_fill += 1

# inbound.csv : 到着日順、1枚=1行
seq = 0
with open(f"{OUT}/inbound.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["product_id", "rank", "card_id", "arrival_date"])
    for d, pid, c in sorted(inbound_events, key=lambda e: (e[0], e[1])):
        for _ in range(c):
            seq += 1
            w.writerow([pid, RANK, f"B{seq:07d}", d])

# orders.csv : 日付順
with open(f"{OUT}/orders.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["order_date", "product_id", "rank", "quantity"])
    for (d, pid) in sorted(order_agg):
        w.writerow([d, pid, RANK, order_agg[(d, pid)]])

print(f"products={len(allpids)} 初期在庫={init_total} 入荷={sum(inbound_total.values())} "
      f"注文行={len(order_agg)} ピーク={peak} 箱={num_boxes}x{BOX_CAPACITY}={cap_total} "
      f"初期使用箱={box_idx}")
