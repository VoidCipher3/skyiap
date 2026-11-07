"""價位對照紀錄：以美區價格級距為單位，記錄各地區的當地價。

只用 Python 標準庫。放在 tools/ 而不是 scripts/：scripts/ 被 .gitignore 排除
（main.py 會把 secret 腳本寫進去），放那裡這支檔案不會進 repo。

規則
- 一列是一個美區價格級距（USD 9.99…），格子是「當下在架、美區標這個價」的商品
  在該區的當地價。不加總、不平均、不取眾數：同一級距若有不同價，全部列出。
- 新增快照的唯一條件：某個 (級距, 地區) 的當地價和上一筆快照時的已知值不同。
  禮包上下架、某級距暫時沒有商品、第一次出現的級距，都不會新增快照，
  只會更新 current 與 known。
- 匯率只跟著快照存（當天的快照），匯率變動本身不新增快照。

輸出 data/tier_history.json
  meta.tiers      固定級距清單（TIERS），從沒出現過的級距前端標「待定」
  current         這次抓取時在架的級距與價格（cells），每次執行都更新
  known           每個 (級距, 地區) 最後一次看到的值與日期
  snapshots[]     只在當地價變動時追加：at / rates / cells / known / changes

第一次執行（檔案不存在）時，用 price_history.json + store_diff.json 的
上架區間（catalog.appearances）回填歷史；之後每次只看這次的 store.json。

用法: python tools/tier_history.py            （在 repo 根目錄）
      python tools/tier_history.py <data_dir>
"""
import copy
import json
import sys
from pathlib import Path

# 固定級距清單。要增減級距只改這一行。
TIERS = ["0.99", "1.99", "2.99", "3.99", "4.99", "6.99", "9.99", "11.99",
         "14.99", "17.99", "19.99", "24.99", "29.99", "49.99"]

SCHEMA = 1
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
OUT = DATA / "tier_history.json"


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def tier_key(usd):
    return f"{float(usd):.2f}"


def norm(v):
    """320.0 -> 320，保留真正的小數。"""
    f = float(v)
    return int(f) if f.is_integer() else f


def build_cells(entries):
    """entries: [(usd_price, {region: local_price})] -> {tier: {region: [distinct sorted]}}"""
    cells = {}
    for usd, prices in entries:
        if usd is None:
            continue
        t = cells.setdefault(tier_key(usd), {})
        for code, p in prices.items():
            if p is None:
                continue
            t.setdefault(code, set()).add(norm(p))
    return {k: {c: sorted(v) for c, v in sorted(r.items())} for k, r in sorted(cells.items(), key=lambda x: float(x[0]))}


def pick_rates(rate_map, currencies):
    if not rate_map:
        return None
    return {c: rate_map[c] for c in sorted(currencies) if c in rate_map}


def step(state, at, cells, rates, rate_meta):
    """處理一個時間點。回傳是否新增了快照。"""
    day = at[:10]
    known = state["known"]
    for tier, regs in cells.items():
        for code, vals in regs.items():
            known.setdefault(tier, {})[code] = {"v": vals, "seen": day}

    snaps = state["snapshots"]
    changes = []
    if snaps:
        prev = snaps[-1]["known"]
        for tier, regs in known.items():
            for code, cur in regs.items():
                old = prev.get(tier, {}).get(code)
                if old is not None and old["v"] != cur["v"]:
                    changes.append({"tier": tier, "region": code, "from": old["v"], "to": cur["v"]})

    state["current"] = {"at": at, "cells": cells, "rates": rates, **rate_meta}
    if snaps and not changes:
        return False
    snaps.append({"at": at, "rates": rates, **rate_meta, "cells": cells,
                  "known": copy.deepcopy(known), "changes": changes, "initial": not snaps})
    return True


def listed_on(catalog, sku, day):
    for a, b in catalog.get(sku, {}).get("appearances", []):
        if a <= day and (b is None or day <= b):
            return True
    return False


def value_at(series, day):
    v = None
    for d, p in series or []:
        if d <= day:
            v = p
        else:
            break
    return v


def backfill(state, history, catalog, currencies):
    series = history.get("series", {})
    rate_snaps = history.get("rates", {})
    days = sorted({d for s in series.values() for ser in s.values() for d, _ in ser})
    added = 0
    for day in days:
        entries = []
        for sku, s in series.items():
            if not listed_on(catalog, sku, day):
                continue
            prices = {code: value_at(ser, day) for code, ser in s.items()}
            entries.append((prices.get("US"), prices))
        r = rate_snaps.get(day)
        meta = {"rate_date": day if r else None, "rate_source": history.get("meta", {}).get("rate_source")}
        added += step(state, day, build_cells(entries), pick_rates(r, currencies), meta)
    return days, added


def strip_volatile(state):
    s = copy.deepcopy(state)
    s.get("meta", {}).pop("updated", None)
    if s.get("current"):
        s["current"].pop("at", None)
    return s


def main():
    store = load("store.json")
    if not store:
        print("tier_history: data/store.json 不存在，跳過")
        return 0
    meta = store.get("meta", {})
    regions = meta.get("regions", [])
    currencies = {r["currency"] for r in regions} | {"USD"}

    old = load("tier_history.json")
    # deepcopy：下面會原地修改 state，不複製的話最後「有沒有變化」永遠比成一樣
    state = copy.deepcopy(old) if old else {"schema": SCHEMA, "meta": {}, "current": None, "known": {}, "snapshots": []}

    if not old:
        history = load("price_history.json", {}) or {}
        catalog = (load("store_diff.json", {}) or {}).get("catalog", {})
        days, added = backfill(state, history, catalog, currencies)
        print(f"tier_history: 回填 {len(days)} 個日期，產生 {added} 筆快照")

    r = meta.get("rates") or {}
    entries = [(it.get("prices", {}).get("US"), it.get("prices", {})) for it in store.get("items", [])]
    added = step(state, meta.get("fetched") or "", build_cells(entries),
                 pick_rates(r.get("rates"), currencies),
                 {"rate_date": r.get("date"), "rate_source": r.get("source")})

    seen = {t for snap in state["snapshots"] for t in snap["cells"]} | set(state["known"])
    state["meta"] = {"updated": meta.get("fetched"), "tiers": TIERS,
                     "regions": regions,
                     "untracked_tiers": sorted(seen - set(TIERS), key=float)}

    if old and strip_volatile(old) == strip_volatile(state):
        print("tier_history: 沒有變化，不改寫")
        return 0
    OUT.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"tier_history: 快照 {len(state['snapshots'])} 筆（本次{'新增 1' if added else '無新增'}），"
          f"未列入 TIERS 的級距 {state['meta']['untracked_tiers'] or '無'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
