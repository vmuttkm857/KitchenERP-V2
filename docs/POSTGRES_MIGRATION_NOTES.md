# KitchenERP SQLite → PostgreSQL 遷移踩坑與 V2 設計準則

> 此文件記錄 A 遷移過程的程式碼證據與歷史問題。目的不是複製 workaround，而是讓 V2 從 PostgreSQL-first 架構避免問題。

## 1. SQL 方言與 DB-API 差異

| 問題 | 發生位置/證據 | 原因 | A 的處理方向 | V2 的根治方式 |
|---|---|---|---|---|
| Placeholder | 各 active page 的 `_placeholder()` / `_db_placeholder()` | SQLite 用 `?`，psycopg 用 `%s` | 每模組判斷 backend | V2 只使用 psycopg/PostgreSQL parameter binding；不保留雙分支 |
| 動態 IN | dish、menu、requirement、purchase 等 `_placeholders` | `IN (?,...)` 不能直接給 PostgreSQL | backend-aware placeholder count | repository 使用統一 SQL builder 或 `= ANY(%s)`（明確型別） |
| `INSERT OR IGNORE` | menu 初始化餐別/日期 | SQLite-only 語法 | PostgreSQL 用 `ON CONFLICT (...) DO NOTHING` 分支 | V2 一律 PostgreSQL `ON CONFLICT`，明確指定 target |
| `lastrowid` | ingredient/dish/menu/requirement/purchase 建立 ID | psycopg 不提供 SQLite lastrowid | PostgreSQL branch 用 `RETURNING` | V2 所有需新 ID 的 INSERT 一律 `RETURNING` |
| `Connection.executemany` | dish/menu/requirement/purchase 批次寫入 | psycopg connection 沒有 sqlite-style `executemany` | 用 `cursor.executemany()` 並 close cursor | repository transaction context 擁有 cursor；批次統一 cursor API |
| `SELECT DISTINCT ... ORDER BY LOWER(...)` | dish recipe supplier query | PostgreSQL 要求 DISTINCT 時 ORDER BY expression 出現在 select list | 改語意正確 query/order | V2 query review/testing lint；可 `ORDER BY supplier_name` under suitable collation 或 select computed sort key |
| `COLLATE NOCASE` | 搜尋/排序 | SQLite collation 名稱不相容 | PostgreSQL `LOWER(column)` 分支 | V2 預設明確 `LOWER`/functional index 或 ICU collation 策略 |
| `BEGIN IMMEDIATE`, PRAGMA, sqlite_master | migrations/SQLite path | SQLite-only locking/schema inspection | backend branch或不在 PG path 執行 | V2 不帶 SQLite migrations；PostgreSQL migrations 由正式工具管理 |

## 2. 型別差異

### NUMERIC / Decimal

- **問題**：PostgreSQL `NUMERIC` 由 psycopg 讀成 `Decimal`；舊程式含 `Decimal * float`、`0.0 + Decimal`、直接餵入 `st.number_input` 等風險。
- **A 處理**：requirement、snapshot、purchase、dish、ingredient 等加入 `_as_decimal`、`_db_numeric`、`_ui_number`；`modules/common/quantity.py` 讓 `ml→L` 的 0.001 對 Decimal 使用 `Decimal(str(...))`。
- **V2**：domain/service/database 一律 Decimal；只在 UI widget 或 Excel 格式化邊界轉 string/float；金額與量不可散落用 Python float。

### DATE / TIMESTAMPTZ

- **問題**：SQLite 回 ISO TEXT，PostgreSQL 回 `datetime.date`/`datetime.datetime`。字串與 date 混作 dict key 時，Excel/週菜單可產生空資料格。
- **A 處理**：各頁 `_as_date`/`_db_date`；menu Excel 用集中 date normalization 修正 mapping key；purchase DateColumn 在 DataFrame 前轉真正 date，寫回時統一 ISO。
- **V2**：API boundary 統一 `date`/timezone-aware datetime；key 建構先 normalise；絕不把 DB date 當文字隱式比較。

### BOOLEAN

- **問題**：SQLite `0/1` 與 PostgreSQL `True/False`；SQL `is_active=1` 及 UI bool 映射不一致。
- **A 處理**：`_db_boolean`、`_active_condition` helper。
- **V2**：資料庫/服務均 bool，SQL 直接 `TRUE/FALSE` 或 bind bool。

### JSON / JSONB

- **問題**：SQLite snapshots 的 TEXT JSON 要 `json.loads`；PostgreSQL JSONB 可能直接讀回 Python list/dict；盲目 loads 會失敗。
- **A 處理**：`_json_safe`、`_db_json(Jsonb(...))`、`decode_json_list` 接受 list/tuple/dict/string。
- **V2**：採 typed JSON schema/Pydantic value objects；儲存時 JSONB，讀取時不二次解析。

## 3. Transaction 與錯誤處理

| 風險 | A 的證據 | V2 設計 |
|---|---|---|
| PostgreSQL statement error 使 transaction aborted | dish/ingredient/menu/requirement/snapshot/purchase 均新增 `except: rollback()` | 每個 command handler 在單一 transaction wrapper 中 commit/rollback/close；catch 前先 rollback |
| 批次部分成功 | recipe batch、snapshot items/schedules、menu copy、purchase order create/delivery | transaction 包住全批；服務先 validate，再寫入；integration test 故意讓第二筆失敗 |
| Constraint 訊息不安全/不精準 | A 的 `_dish_error_message`、`_requirement_error_message` 等 | 以 SQLSTATE/constraint name 映射可讀錯誤；絕不顯示 connection URL/原始 DB 例外給使用者 |
| 單一 cursor lifecycle | PostgreSQL `executemany` 與 profile wrapper | cursor 用 context manager/try-finally，不能依賴 connection.execute 回傳形態 |
| PostgreSQL ON DELETE 與 SQLite 實際不同 | snapshots/items cascade、purchase items/allocations cascade | 在 schema 中明確 policy；每個 delete flow 做 transaction + regression |

## 4. Connection 與 Streamlit 效能

### 已觀察到的問題

1. SQLite 時 `connect → query → close` 成本低；Supabase 遠端單一 SELECT 約 85–90 ms，重複 SQL 會主導 LAG。
2. 初始每個 `get_connection()` 都可能開遠端 TCP/SSL；A 後來導入 lazy process-level `psycopg_pool.ConnectionPool`。
3. pool 初版曾發生 lease 沒有正確 return 的 connection leak；A 現在以 `_PooledConnectionProxy.close()` rollback 未完成交易後 `putconn()`。
4. Streamlit rerun、tab/expander eager render、Dialog 與逐列 widget 會把一次使用者操作放大為多次 query。

### A 的防護/量測

- `database/connection.py` 的 `ERP_DB_PROFILE=1`：只記 operation、耗時、connection/SQL aggregate，不列 SQL、參數或 DATABASE_URL。
- menu active workspace 將同 rerun 的 meal types/weekly content 重用，避免每次 initialize query。
- recipe、menu add-dishes 使用 lazy preview/小型最近快取，而不是預載所有配方。

### V2 建議

- process-scoped managed pool + request-scoped transaction/connection lifecycle；不讓 UI 隨意取得 raw connection。
- repository/service API 一次取得畫面需要的 aggregates，避免 N+1。
- lookup cache 只用於低變動資料（categories、supplier options），每個 command 成功後精確 invalidation；不 cache 即時週菜單/配送。
- 統一採 telemetry middleware，避免散落 profile wrapper。

## 5. Schema 演進與 mismatch

### 發現模式

- SQLite 的 `init_db.py` 是早期基礎，功能欄位透過多支 `migrate_*.py` 後續加上；直接以 init 建新庫可能漏掉菜色/菜單分類、loss rate、採購規格、snapshot、purchase、排序與來源追蹤欄位。
- PostgreSQL `001_initial_schema.sql` 一次包含完整目標欄位、constraints與 indexes；Python INSERT 若少送 PostgreSQL NOT NULL 欄位會立刻失敗。

### V2 避免方式

1. 只維護一套 declarative PostgreSQL migration history（例如 Alembic/SQL migrations）。
2. 每次應用啟動不做 schema mutation；部署 pipeline 先跑 migration。
3. repository INSERT/UPDATE 與 schema contract 有 schema-level integration tests。
4. 以 typed DTO/command 顯式列出 required values，避免 `SELECT *`/隱式 default 假設。

## 6. 其他 PostgreSQL 相容性清單

- dict row：`fetchone()[0]`/`row[0]` 對 dict_row 不可靠；A 改 COUNT alias + named access，例如 `row['dish_count']`。
- `LIMIT/OFFSET`：必須使用 backend 參數 placeholder，且 offset = `(page-1)*page_size`；0 筆時 total pages 安全取 1/空結果 UI。
- 搜尋：使用 `LOWER(column) LIKE LOWER(%s)`，不要依賴 SQLite nocase。
- `CURRENT_TIMESTAMP` 可保留，兩 backend 都可用；但 V2 的時間語意應由 PostgreSQL TIMESTAMPTZ 與明確 timezone policy 定義。
- A 的 `_BackendConnection`/per-module helper 是遷移過渡層；V2 不應將每頁 SQL adapter 當架構。

## 7. V2 遷移原則（精簡版）

1. PostgreSQL-only SQL、psycopg-only data access，無 SQLite fallback。
2. domain Decimal/date/bool/JSON typed；UI 是最後一層展示/輸入轉換。
3. transaction ownership 在 service；repository 不自行 commit（除明確 command wrapper）。
4. DB constraints + mapped domain exceptions + integration tests。
5. query budgets：每個主要頁面定義目標 SQL 次數與 profiling gate，阻止 rerun N+1 回歸。
6. 先建立完整 schema，再寫業務服務，杜絕「Python 寫入與 migration 先後不一致」。
