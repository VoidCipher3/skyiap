# Sky 商城各地區定價對照

比較《光·遇》商城同一件商品在 **37 個地區**的定價，支援匯率換算、每燭單價、
價格走勢、調價與匯率拆解、變更歷史。純靜態站，資料由 GitHub Actions 定時抓取。

**非官方專案，與 thatgamecompany 無關。資料來自官方商城的 API。**
此站僅供查詢比較，不提供購買或跨區下單功能。

[連結](https://voidcipher3.github.io/skyiap)
---

## 結構

```
index.html                語言跳轉
tw/ cn/ en/ ja/ ko/       五種語言的頁面（內容由 app.js 填）
assets/app.js             全部前端邏輯，無框架、無 CDN
assets/style.css          全部樣式，無外部相依
assets/i18n/{lang}.json   介面字串。加一種語言 = 加一個檔
scripts/fetch_store.py    抓取腳本，只用 Python 標準庫
scripts/lifecycle.py      蠟燭解析 / 上架履歷 / 時間線 / 匯率拆解
scripts/probe_api.py      一次性調查工具：哪些地區有獨立定價、哪些語言真的有翻譯
scripts/make_demo_data.py 產生模擬資料給本機預覽
data/store.json           商品 + 各地區價格（可重建）
data/store_diff.json      變更、歷史、上架履歷（累積，無法重建）
data/price_history.json   價格時間線 + 各日匯率快照（累積，無法重建）
data/desc.{lang}.json     完整說明，前端按語言分別載入
data/tier_history.json    價位對照紀錄（累積，第一次執行時從既有歷史回填）
tools/tier_history.py     產生 tier_history.json，只用 Python 標準庫
CHANGELOG.md              網站版本紀錄
worker/                   Cloudflare Worker：定時排程 + 密碼手動刷新
```
---
## 功能

| | |
|---|---|
| 地區挑選 | 37 個 chips 自由勾選，可全選／全不選／回預設，選擇存 localStorage |
| 最划算 / 最貴 | 每列自動標綠（最低）紅（最高），另有最低／最高／價差三欄 |
| 每燭單價 | 從商品名／描述解析支數，欄位排在商品名後面，可據此排序 |
| 換算 | 基準幣下拉 + 「換算後／原幣」切換；換算後每格下方仍附原幣小字 |
| 檢索 | 搜尋比對全部語言的名稱＋sku；分類 chips；「僅限時販售中」 |
| 排序 | 最低價升冪／降冪、跨區價差、每燭單價、名稱、分類 |
| 倒數 | 限時商品顯示距離結束還有多久，每秒跳動 |
| 上架履歷 | 第幾次上架、上次下架於何時、已下架幾天 |
| 標籤徽章 | 網頁限定、免費、可用次數、Switch 平台限制；某區買不到會壓暗加刪除線 |
| 商品明細 | 點名稱開視窗：官方預覽動畫、完整說明、走勢圖、資料點清單、匯率拆解 |
| 變更 / 歷史 | 新增／下架／改價（紅漲綠跌），含商品圖片，最多 200 筆可展開 |
| 分享連結 | 地區、基準幣、排序、搜尋等狀態都寫進網址 |
| 語言 | tw / cn / en / ja / ko |
| 價位對照 | 以美區價格級距為列，列出各地區當地價；選兩個時間點對照，可勾選「比較匯率」 |
| 版本 | 網站版本紀錄，五種語言 |

---

## 價位對照（v1.5）

`tools/tier_history.py` 在 `main.py` 之後執行（見 `fetch.yml`），讀 `data/store.json`
寫 `data/tier_history.json`。放在 `tools/` 而不是 `scripts/`：`scripts/` 在 `.gitignore`
裡（`main.py` 會把 secret 腳本寫進去），放那裡不會進 repo。

- 一列是一個美區價格級距，格子是當下在架、美區標這個價的商品在該區的當地價。
  不加總、不平均、不取眾數；同一級距出現不同價時全部列出。
- **只有當地價變動才新增快照**。禮包上下架、級距暫時沒有商品、第一次出現的級距，
  都只更新 `current` / `known`，不新增快照。匯率跟著快照存，匯率變動本身不算。
- 「待定」：所有紀錄都沒出現過的級距。「當前無禮包」：出現過，但該時間點沒有在架商品，
  格子附最後一次看到的值與日期。
- 「比較匯率」勾選後，每個時間點用自己的匯率快照換算；變動標記仍只看當地價。
- 固定級距清單在 `tools/tier_history.py` 的 `TIERS`，增減級距只改那一行。
  實際出現但不在清單裡的級距仍會記錄並顯示，同時列在 `meta.untracked_tiers`。
- `data/tier_history.json` 不存在時，用 `price_history.json` 加上 `store_diff.json`
  的上架區間（`catalog.appearances`）回填；只算當天在架的商品，已下架商品殘留的舊價不會混進來。
- 腳本失敗不會擋住價格更新（`continue-on-error`）。

## 版本紀錄

網站「版本」分頁的內容在 `assets/i18n/{lang}.json` 的 `changelog`；
`CHANGELOG.md` 是繁中版本，改版時兩邊一起更新。
