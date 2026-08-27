# KitchenERP V1 功能盤點

> 產生日期：2026-08-28。  
> 比較基準：`KitchenERP_backup_before_postgres`（B，業務功能基準）與 `KitchenERP`（A，PostgreSQL 遷移中版本）。  
> 證據來源：兩個版本的 `app.py` 實際路由、各 active `modules/*/page.py`、`database/init_db.py`、SQLite migrations、A 的 `database/postgresql/001_initial_schema.sql`。未依 README 或備份檔推論。

## 1. Active 功能地圖

兩版 `app.py` 均實際載入以下頁面：分類管理、供應商管理、食材資料庫、菜色管理、菜單管理、廚房作業、食材需求、需求確認、採購管理。B 已包含完整主流程；A 的主要差異是 PostgreSQL 兼容、資料型別邊界與少量後續 UX/效能修正。

| 模組 | 使用者可做什麼 | 主要資料 | 依賴/輸出 | A/B 差異 |
|---|---|---|---|---|
| 分類管理 | 新增、搜尋、選取、修改、停用/恢復食材分類；新增與批次修改菜色分類 | `categories`, `dish_categories` | 食材與菜色分類選項 | 功能相同；A 增加 PostgreSQL placeholder、boolean、錯誤訊息處理 |
| 供應商管理 | 搜尋、狀態篩選、分頁、選取供應商、完整資料修改、停用/恢復、新增 | `suppliers` | 食材主供應商；採購/備料顯示名稱 | 功能相同；A 為 PostgreSQL 與分頁輸入同步補強 |
| 食材資料庫 | 新增食材與初始價格、列表搜尋/分類/狀態/分頁、修改主檔、停用/恢復、查看價格歷史、更新目前單價並追加歷史 | `ingredients`, `ingredient_price_history`, `categories`, `suppliers` | 配方、需求、成本、採購 | 功能相同；A 保留新增失敗草稿、Decimal/DATE/constraint 相容 |
| 菜色管理 | 新增/修改/停用菜色、分類、列表分頁、逐列「編輯」與「配方」、標準配方新增/批改/批刪、每份成本 | `dishes`, `dish_ingredients`, `ingredients`, `dish_categories`, `suppliers` | 菜單、需求、備料 | A 後續配方 Dialog、供應商篩選、分頁與 PostgreSQL 修正；核心規則相同 |
| 菜單管理 | 新增/分類/啟停菜單、列表分頁、編輯週菜單、動態餐別、每餐格加菜/管理、排序、人數、備註、批次刪除、複製日/整週、Excel 兩種匯出 | `menus`, `menu_categories`, `menu_meal_types`, `menu_days`, `menu_dishes`, `dishes` | 廚房、需求 | B 已有功能；A 另有 PostgreSQL date key、Dialog/SQL 效能等修正 |
| 廚房作業 | 選菜單與範圍（單餐/單日/整張）、依菜色/食材/供應商看備料、未建配方警示、列印 Excel、整週配料總覽 | 菜單、菜色、配方、食材、供應商 | 作業與 Excel，不寫 DB | B 已有；A 有顯示小數格式、匯出 UI、PostgreSQL date 相容調整 |
| 食材需求 | 多選菜單/分類/日期、快速加入指定日全部菜單、彙總或明細需求、成本與單位待確認警示、確認為需求快照 | 菜單、配方、食材、供應商、快照 | `requirement_snapshots` 與 items/schedules | B 主邏輯已存在；A 支援 PostgreSQL JSONB/Decimal/date，並完成分類多選 UX |
| 需求確認 | 篩選/選取快照、依狀態分工作與歷史、查看 hard copy、調整採購數量/單位、建立正式叫貨單、刪除未建單快照 | snapshots/items/schedules, purchase orders | 正式採購單 | B 已有核心；A 增加 PostgreSQL 及 snapshot 狀態 selector |
| 採購管理 | 建立/補建正式採購單、工作匣、結案/恢復/刪除、每日叫貨、明細/叫貨表/帳務/分帳呈現、配送調整、Excel、採購總表 | purchase orders/items/allocations | 以 snapshot hard copy 作來源 | B 已有；A 補 DATE/Decimal/JSONB/PostgreSQL 與 UI 分層 |

## 2. 模組操作流程

### 2.1 分類、供應商、食材主檔

1. 先維護食材分類、菜色分類與供應商。
2. 建立食材時輸入代碼、名稱、食材分類、基本單位、目前單價、可選主供應商與備註。
3. 新增食材與其首筆價格歷史在同一交易中完成；日後改單價會同時更新 `ingredients.current_price` 並追加價格歷史。
4. 停用主檔不搬移既有引用或歷史資料；列表可查啟用、停用或全部。

特殊 UI：主檔皆有搜尋、狀態篩選、SQL COUNT/LIMIT/OFFSET；供應商與食材採「列表選取後顯示完整資料」而非永遠展開大量卡片。

### 2.2 菜色與標準配方

1. 建立菜色（唯一代碼、唯一名稱、可選菜色分類、備註、啟用狀態）。
2. 由菜色列表的配方入口開啟單一道菜的標準配方 Dialog。
3. 左側維護既有配方：每人用量、**配方單位**、耗損率、備註及多筆刪除；右側按供應商/關鍵字分頁找食材，勾選後批次加入。
4. 配方只保存 `ingredient_id`；供應商是由食材主檔 `primary_supplier_id` 顯示，不複製到配方。
5. 單份標準成本按配方量（含耗損）換到食材基本單位後，乘食材目前單價；不能安全換算時顯示警示而非猜測。

特殊 UI：已加入的 ingredient 不可再次勾選；搜尋、供應商、頁碼是 SQL 分頁；連續儲存/刪除/加入後應維持同一菜色的 Dialog。

### 2.3 菜單與週菜單

1. 建立有名稱、起訖日、可選分類及備註的菜單。
2. 每張菜單有可排序、可停用並可重新啟用的餐別。新菜單在首次開啟週工作區時建立預設餐別。
3. 週矩陣以日期 × 餐別顯示，每餐格可直接「管理」或「＋加菜」；餐格的菜色以 `menu_dish_id` 操作。
4. 加菜工作區保留跨搜尋、分類、分頁的每餐格獨立 basket；可看單一道菜的 lazy recipe preview。
5. 管理工作區可改每道菜的人數、備註、順序（數字或上下移）、批次刪除；所有批次寫入採 transaction。
6. 支援同菜單/跨菜單的一天複製及整週複製；來源/目的餐別按名稱對應。覆蓋必須二次確認，加入模式不重複 `(日期, 餐別, dish_id)`。
7. 支援可編輯與列印版週菜單 Excel。

### 2.4 廚房作業／備料單

1. 選菜單、範圍（單餐、單日、整張菜單）、顯示視角（依菜色、依食材、依供應商）及顯示單位模式。
2. 由菜單＋配方即時計算備料，不讀採購單或實際叫貨量。
3. 顯示沒有配方、找不到食材、不可換算單位等警示。
4. 依當前範圍直接下載 A4 列印 Excel；整張菜單另可下載整週菜單配料總覽。

### 2.5 食材需求 → 快照 → 採購

1. 在食材需求選擇候選菜單（可多分類、多菜單），再選需求日期；「快速加入整日菜單」只把符合日期範圍的 menu ID 合併到目前選取。
2. 系統以配方與排餐產生彙總或明細需求；單位不能換到食材基本單位時標記待確認，不提供估算採購/成本。
3. 「確認需求」把結果寫成 snapshot hard copy，包括選取菜單/日期、每項數量、採購資料與逐日 schedule。
4. 需求確認頁可調整快照的人工採購量與採購單位，但不回寫原需求/食材/配方。未建正式叫貨單的快照可以刪除；已建單者保留。
5. 由快照建立正式採購單，複製為 order/items/allocations。採購頁管理每日叫貨、供應商/日期顯示、配送拆分、結案與 Excel。

## 3. A 與 B 比較結論

### 已確認相同的業務能力

兩版都已包含九個 active 模組、上述完整工作流、SQLite migrations、菜單分類/菜色分類、配方單位、耗損、快照、正式採購單、配送與廚房 Excel。B 因此是可信的 V2 商業能力基準。

### A 已確認的新增/變更

| 類別 | A 的內容 | 判定 |
|---|---|---|
| PostgreSQL 支援 | `database/connection.py`、每頁的 placeholder/boolean/date/Decimal/JSON helper、RETURNING、cursor.executemany、pool/profiling | **DB engine 兼容，不是 V2 business rule** |
| 資料型別安全 | DATE/TIMESTAMPTZ、NUMERIC/Decimal、JSONB、dict row、constraint error 映射 | **應吸收為 V2 的 PostgreSQL-first 技術要求** |
| 菜單/配方 UI 細節 | Dialog 連續操作、lazy recipe preview、小型 preview cache、列表 direct page input、菜單/週工作區低 SQL 改善 | **可保留為 V2 UX/效能要求**；不必沿用舊 Session State 實作 |
| 廚房 Excel 細節 | A4 分頁、每頁頁首、菜色不跨頁、數字至多兩位、直接下載流程、整週總覽只在整張菜單範圍顯示 | **建議保留行為** |

### 待確認事項

- A/B 同名函式的許多差異是 PostgreSQL 改寫與 UI 修補交疊；沒有獨立需求文件或完整雙庫 runtime regression 時，無法保證每一項微小畫面行為都是有意的 business-rule 改變。
- A 的 `modules/menu/page.py`、`modules/dish/page.py` 留有前段 legacy 定義和後段 active 定義；V2 不應複製此結構，但需先以本套文件的行為作驗收基準。

## 4. V2 應保留、但不應照搬的內容

- 保留真正 ID、FK 關聯、hard-copy 歷史、交易原子性、批次操作、不可安全換算即待確認、搜尋與分頁等語意。
- 不照搬 A 的 SQLite/PostgreSQL 分支、`?/%s` 包裝、legacy duplicate definitions、以大量 widget key 避免 rerun 的歷史補丁、或以 session state 補 DB 設計缺口。
- V2 從第一天以 PostgreSQL schema/typed domain model/repository transaction 為唯一資料路徑，UI 只消費明確的 application service。
