# KitchenERP V2 架構規範

> 狀態：架構基準（Architecture Baseline）  
> 適用範圍：KitchenERP V2 的所有程式、資料庫 migration、測試與技術文件  
> 規格來源：`docs/V1_FUNCTIONS.md`、`docs/BUSINESS_RULES.md`、`docs/DATABASE_SCHEMA.md`、`docs/POSTGRES_MIGRATION_NOTES.md`、`docs/V2_REGRESSION_REQUIREMENTS.md`

## 0. Codex 與開發者修改前必讀

任何人或 Codex 在修改 KitchenERP V2 前，必須先閱讀本文件及與本次工作相關的 `docs/` 規格。若實作需求與本文件衝突，必須先更新架構決策並取得確認，不得在程式中偷偷繞過規範。

以下規則不可因趕進度省略：

1. 固定使用 React + TypeScript、FastAPI + Python、PostgreSQL、SQLAlchemy 2.x、Alembic、pytest。
2. 系統採 Modular Monolith；不使用 microservices、Kubernetes；沒有實證需求時不加入 Redis。
3. PostgreSQL 是唯一資料庫，不建立 SQLite 相容層。
4. React 與未來其他 client 只能透過 Backend API 存取資料。
5. Backend 依賴方向固定為 `API → Service → Repository → PostgreSQL`。
6. API route 不含 SQL 與核心業務規則；Service 不含 HTTP 與前端狀態；Repository 不決定業務規則。
7. 所有 schema 變更只透過 Alembic migration。
8. 核心計算、交易與回歸規則必須有 automated tests。
9. 數量與金額在 Backend domain 與 DB 使用 `Decimal` / PostgreSQL `NUMERIC`，API 一律以 decimal string 傳輸；日期、布林、JSON 使用明確型別。
10. 不建立大型 all-in-one page、service、repository 或 model module。

## 1. 系統邊界與部署模型

```text
React Web ───────┐
                 │ HTTPS / versioned JSON API
Future Mobile ──┼────────→ FastAPI Modular Monolith ─→ PostgreSQL
                 │           API → Service → Repository
Other Client ───┘
```

- Frontend 是獨立 client，不知道資料表、SQLAlchemy model 或 DB credentials。
- Backend 是唯一業務規則與資料存取入口。
- PostgreSQL 不對瀏覽器或手機公開，只允許 Backend 使用受限帳號連線。
- 3–5 人使用採單一 Backend application + managed connection pool 即足夠；可依部署環境使用少量 worker，但不以分散式架構為前提。
- 設定由環境變數提供，秘密不得進入 repository、前端 bundle、log 或 API error。

## 2. Frontend 目錄結構

```text
frontend/
├─ src/
│  ├─ app/                    # app bootstrap、router、全域 providers、error boundary
│  ├─ api/                    # 共用 HTTP client、auth token handling、API error mapping
│  ├─ auth/                   # 登入狀態與 route guard；不保存授權規則本體
│  ├─ features/
│  │  ├─ users/
│  │  ├─ categories/
│  │  ├─ suppliers/
│  │  ├─ ingredients/
│  │  ├─ dishes/
│  │  ├─ recipes/
│  │  ├─ menus/
│  │  ├─ kitchen-operations/
│  │  ├─ requirements/
│  │  ├─ snapshots/
│  │  └─ purchases/
│  ├─ components/             # 無 domain 意義的共用 UI 元件
│  ├─ hooks/                  # 無 domain 意義的共用 hooks
│  ├─ types/                  # 跨 feature 的 client-only type；API type 優先由契約產生
│  ├─ utils/                  # 純展示工具；禁止複製 Backend business rules
│  ├─ styles/
│  └─ test/                   # test setup、fixtures、mock server
└─ tests/                     # 跨 feature integration / E2E tests
```

每個 `features/<domain>/` 可含 `api/`、`components/`、`pages/`、`hooks/`、`types/`、`tests/`，只建立實際需要的子目錄。頁面負責組合與互動，不得重算需求、成本、單位換算、採購上限等規則。前端暫存 basket、草稿與篩選條件屬 client UI state；完成命令仍由 Backend 驗證。

## 3. Backend 目錄結構

```text
backend/
├─ app/
│  ├─ main.py                 # application composition root
│  ├─ core/                   # config、security primitives、logging、errors、telemetry
│  ├─ db/
│  │  ├─ base.py              # SQLAlchemy declarative base
│  │  ├─ session.py           # engine/pool、request-scoped session lifecycle
│  │  └─ unit_of_work.py      # transaction boundary abstraction
│  ├─ api/
│  │  ├─ dependencies.py      # auth/session/service dependency wiring
│  │  └─ v1/                  # versioned public API router composition
│  ├─ domains/
│  │  ├─ auth/
│  │  ├─ users/
│  │  ├─ categories/
│  │  ├─ suppliers/
│  │  ├─ ingredients/
│  │  ├─ dishes/
│  │  ├─ recipes/
│  │  ├─ menus/
│  │  ├─ kitchen_operations/
│  │  ├─ requirements/
│  │  ├─ snapshots/
│  │  └─ purchases/
│  └─ shared/
│     ├─ domain/              # Decimal quantity、money、unit conversion 等純 domain primitives
│     ├─ pagination/          # 統一分頁 contract
│     └─ exports/             # 安全 Excel primitives；domain 決定內容、此處處理格式
├─ migrations/
│  ├─ env.py
│  └─ versions/
└─ tests/
   ├─ unit/
   ├─ integration/
   ├─ api/
   ├─ contract/
   ├─ regression/
   └─ performance/
```

每個 `domains/<domain>/` 依需要包含：

```text
api.py             # route 與 HTTP DTO mapping
schemas.py         # Pydantic request/response schema
service.py         # use cases、business rules、transaction orchestration
repository.py      # repository protocol / data-access implementation（可再拆分）
models.py          # 該 domain 的 SQLAlchemy persistence models
entities.py        # 必要時使用的純 domain entity/value object
exceptions.py      # domain-specific errors
```

檔案成長後依 use case 拆分，例如 `services/copy_menu.py`，不得累積成單一巨大 module。SQLAlchemy models 是 persistence concern，不可直接作為 public API response。

## 4. Domain / Module 分界

| Domain | 擁有責任與資料 | 不負責 |
|---|---|---|
| `auth` | 登入、登出、密碼 hash 驗證、token/session lifecycle、current principal | user 主檔管理、各 domain 規則 |
| `users` | 帳號、顯示名稱、角色、啟停、管理者操作 | 密碼演算法細節、ERP domain 資料 |
| `categories` | 食材分類、菜色分類、菜單分類及其排序/啟停 | 食材、菜色、菜單生命週期 |
| `suppliers` | 供應商主檔與啟停 | 採購計算、配方供應商複製 |
| `ingredients` | 食材主檔、採購規格、目前價格、價格歷史的原子更新 | 配方、需求彙總、正式採購 |
| `dishes` | 菜色主檔與分類關聯 | 配方內容、菜單排程 |
| `recipes` | 菜色－食材配方、配方單位、耗損、單份成本 | 食材主檔修改、需求快照 |
| `menus` | 菜單、動態餐別、日期餐格、菜色、人數、排序、日/週複製 | 需求與採購計算 |
| `kitchen_operations` | 由菜單與配方產生只讀備料 view、分組及 Excel | 保存需求或讀採購數量 |
| `requirements` | 候選選取、需求計算、警示、彙總/明細 preview | hard-copy lifecycle、採購單管理 |
| `snapshots` | requirement hard copy、items/schedules、人工採購調整、可刪除條件 | 回寫原菜單/配方/食材、正式採購後續管理 |
| `purchases` | 由快照建立第二層 hard copy、正式品項、配送 allocation、結案/恢復/刪除、採購 Excel | 修改來源 snapshot 或主檔 |

`kitchen_operations` 是明確的讀取/報表 domain，因其公式與輸出有獨立驗收規則，不併入 UI helper。`recipes` 與 `dishes` 分開，避免主檔 CRUD 與配方計算/批次交易形成大型 service。三種 category 可在同一 domain 內分成獨立 service/repository，不能以一個含型別分支的萬用資料表或萬用 service 混合語意。

## 5. API、Service、Repository 責任

### API layer

- 定義 versioned endpoint、Pydantic request/response、HTTP status、pagination query。
- 驗證輸入形狀、解析 authenticated principal、呼叫一個 application use case。
- 將 domain exception 映射為穩定、安全的 API error code；不得回傳 raw DB error。
- 不寫 SQL、不開 transaction、不執行核心計算、不依 React 畫面流程設計 private shortcut。

### Service layer

- 擁有 use case、business rule、授權判斷、跨 repository 協調及 transaction boundary。
- command 先驗證再於單一 Unit of Work 內完成；任何一步失敗 rollback。
- query service 回傳畫面/手機實際需要的 DTO aggregate，避免 client 逐列補查。
- 單位換算、耗損、成本、需求、配送上限等純計算集中使用 `shared/domain` 的唯一實作。
- 不知道 HTTP、React state，不寫原生 SQL，不依賴具體 driver 行為。

### Repository layer

- 唯一資料庫讀寫位置；使用 SQLAlchemy 2.x 與 PostgreSQL semantics。
- 提供 use-case-oriented 方法、投影、SQL pagination、bulk operation、row locking（必要時）與 eager loading。
- 不自行 commit；使用 Service 擁有的 Unit of Work / Session。
- 不決定 business policy；只實現查詢、持久化與 constraint-backed guarantees。
- 不回傳可被 API 任意 lazy-load 的 ORM graph；Session 離開 request 後不可外洩。

## 6. Authentication / Users

- `auth` 與 `users` 是獨立但相鄰 domain：`auth` 驗證 credentials 與建立 principal，`users` 管理帳號資料與狀態。
- 密碼只保存強式 password hash；不記錄 plaintext、可逆密碼或密碼內容。
- Web 與未來 Mobile 固定採 Access Token + Refresh Token 架構；具體有效期、rotation、撤銷與儲存安全細節於 auth domain 實作時依安全威脅模型定義。
- 初期角色固定為 `admin`、`user`，暫不建立複雜 RBAC；授權永遠由 Backend enforcement，React route guard 只改善 UX。
- API dependency 解析 current principal；Service 再檢查 use-case permission，避免只靠 route 或前端按鈕。
- 重要主表預留 `created_by`、`updated_by`，但目前不建立完整 audit-log subsystem。
- Hard Delete 的密碼重新驗證使用目前登入帳號密碼，只能由 Backend/Auth Service 驗證；Frontend 不得自行比對密碼。
- public API contract 必須與特定 React 實作解耦，讓 Mobile 共用相同 authentication 與 authorization。

## 7. Database 與 Migration

- `backend/app/db` 只放 engine、pool、Session、Unit of Work 等基礎設施；domain models 由各 domain 擁有。
- Alembic 位於 `backend/migrations`；每次 schema 修改一個可審查 revision，含必要 upgrade/downgrade 或明確不可逆說明。
- application 啟動不得自動建表或修改 schema；部署先執行 migration，再啟動相容版本。
- PostgreSQL 使用 `DATE`、`TIMESTAMPTZ`、`BOOLEAN`、`NUMERIC`、`JSONB` 與明確 FK/UNIQUE/CHECK/ON DELETE policy。
- timestamp 統一以 UTC 儲存；Frontend 預設以 `Asia/Taipei` 顯示。菜單日期、供餐日期等純業務日期使用 `DATE`，不得轉換時區或混成 timestamp/string。
- 精確數量與金額使用 `NUMERIC` / Python `Decimal`，API 以字串（例如 `"12.50"`）傳輸，禁止依賴 JavaScript floating point。
- Foreign Key 預設 `RESTRICT`；只有真正 owner-child lifecycle 的純明細可使用 `ON DELETE CASCADE`。Snapshot、採購歷史與正式業務紀錄不得因主檔刪除而連帶消失。
- V2 `menu_days.menu_meal_type_id` 必須以正式 FK 指向 `menu_meal_types.id`，不再以餐別名稱作 relation；複製時仍可依規格用餐別名稱做跨菜單 matching，但寫入使用 ID。
- `dish_categories` 必須包含 `sort_order`。
- 搜尋、列表與 workflow query 的 indexes 由實際 query 與 `EXPLAIN ANALYZE` 驗證；不盲目照搬 V1 index。
- hard copy 表保留文字與數值歷史；source ID 是否為 FK 依歷史保留語意決定，不能為追求正規化破壞 snapshot/order 不變性。
- constraint name 必須穩定，供 Backend 依 SQLSTATE + constraint name 映射可讀錯誤。

## 8. Testing 結構與門檻

- `unit/`：純 Service/domain 計算；單位、耗損、成本、需求、排序、採購上限等不連 DB。
- `integration/`：只對 PostgreSQL 測 Repository、constraints、transactions、Alembic schema contract；不使用 SQLite substitute。
- `api/`：認證、授權、validation、error mapping、pagination 與完整 use case。
- `contract/`：OpenAPI 與 client contract 相容性，支援 Web 與未來 Mobile。
- `regression/`：逐項對應 `V2_REGRESSION_REQUIREMENTS.md` 的跨 domain 情境。
- `performance/`：主要 endpoint query count/query budget、N+1、大分頁與代表性資料量。
- batch transaction 測試必須故意令中途一筆失敗，證明沒有部分寫入。
- migration CI 必須能從空 PostgreSQL 升到 head；必要時另測前一 revision 升級。

## 9. 允許的 Domain 依賴

```text
auth → users
ingredients → categories, suppliers
dishes → categories
recipes → dishes, ingredients, shared.domain
menus → categories, dishes
kitchen_operations → menus, recipes, ingredients, suppliers, shared.domain
requirements → menus, recipes, ingredients, suppliers, shared.domain
snapshots → requirements（建立時的結果 contract）, shared.domain
purchases → snapshots（建立時的 immutable contract）, shared.domain
```

依賴規則：

1. 依賴 domain 的公開 service/query contract 或 read model，不直接 import 對方 repository 或任意操作對方 table。
2. 禁止循環依賴。若兩方共享純概念，抽到小型 `shared/domain`；不得把業務 use case 丟入巨大 `common`。
3. 下游 hard-copy domain 只能在建立時讀上游資料；建立後以自己的 snapshot/order 資料為準。
4. `requirements` 不依賴 `snapshots`；`snapshots` 不依賴 `purchases` 來決定寫入，但可透過 purchases 提供的存在性 query 判斷生命週期，或由 application query composition 完成，避免逆向 repository import。
5. `kitchen_operations` 與 `requirements` 共用唯一純計算 primitives，但各自擁有輸出 use case；備料不得讀取 snapshots/purchases。

## 10. 效能、連線與 V1 問題的預防

### 避免 repeated query / N+1

- 以畫面 use case 設計 aggregate endpoint，例如週工作區一次取得日期、餐別、餐格與菜色，而非每格呼叫 API。
- Repository 以明確 projection、join/select-in loading、batch query 取得當頁資料；列表一律 server-side filter/count/pagination。
- lazy recipe preview 可使用獨立按需 endpoint；不得首頁預載所有配方。
- 每個主要 endpoint 設 query budget 並在測試/telemetry 量測，回歸時能直接發現 SQL 次數增加。

### 避免 Streamlit rerun 問題

- React 僅在 query key 或 command 成功後重新取得相關資料，不因任意 widget 改變重跑整頁 Python。
- basket、尚未提交的表單、搜尋與頁碼留在 feature state；資料命令成功後精確 invalidation。
- API command 支援可重試安全性；快照等高風險建立流程需在產品確認後使用 idempotency key / database uniqueness，而非依 UI session flag。

### 避免 connection 問題

- SQLAlchemy Engine / pool 為 process-scoped；Session / transaction 為 request-scoped，於 dependency finally 中確實 rollback/close/return。
- 不讓 React、route 或 Service 取得 raw connection；Repository 共用同一 Unit of Work Session。
- 設 pool size、overflow、timeout、recycle/pre-ping 需依部署與 PostgreSQL connection limit 實測，不硬編碼 V1 workaround。
- telemetry 記 endpoint、query count、DB duration、pool wait、error category；不記 SQL parameters、密碼、token 或 `DATABASE_URL`。
- 低變動 lookup 如分類/供應商選項，先以 HTTP/client cache 與精確 invalidation 解決；無實證前不引入 Redis。即時週菜單與配送不做不透明 server cache。

## 11. API 設計與未來 Mobile 共用

- 所有 public endpoint 放在 `/api/v1`，使用資源與 use-case 語意，不使用 React page 名稱。
- OpenAPI 是 client contract；request/response schema 與 ORM model 分離，必要時由 OpenAPI 產生 TypeScript/mobile client。
- 回傳穩定 ID、ISO date/time、明確 Decimal 序列化策略、pagination metadata 與 machine-readable error code。
- Backend 是唯一 validation、授權與 business-rule authority；手機 App 不需重寫計算。
- API 不依 cookie-only browser assumption；最終 auth transport 需同時評估 Web 安全與 mobile token lifecycle。
- breaking change 以新 API version 或相容演進處理；Web 與 Mobile 可不同發布週期。
- Excel/檔案下載由 authenticated API 提供，Content-Type/filename 明確，不由 React 重建報表規則。

## 12. 架構級交易邊界

以下 use case 必須是單一 transaction：

- 新增食材 + 初始價格歷史。
- 更新目前單價 + 追加價格歷史。
- 配方批次新增/更新/刪除。
- 餐格批次加菜、批次修改/刪除 + 排序正規化。
- 一日覆蓋複製、整週複製。
- 建立 requirement snapshot + items + schedules。
- snapshot 人工採購調整的一致更新。
- 建立 purchase order + items + allocations。
- 配送批次調整及訂購量上限驗證。

DB constraints 是並行寫入的最後防線；Service validation 提供完整規則與可讀錯誤。交易擁有者是 Service/Unit of Work，Repository 不自行 commit。

## 13. Delete Policy

每個 domain 實作時必須明確標記每個刪除 use case 屬於下列一類，不得使用一套萬用 delete：

1. **Relationship Removal / Edit Removal**：移除 owner-child 明細或關聯，例如 menu dish、recipe detail。一般確認即可，不重新驗證密碼；只刪關聯/明細，不刪 master data。
2. **Soft Delete / Deactivate**：ingredient、supplier、dish、category、meal type、user 等正式主檔以 `is_active=false` 或等價機制停用。一般確認即可；停用後不得供新資料選用，既有歷史與 FK 必須仍可顯示。
3. **Hard Delete**：只有未被正式業務資料引用、Service policy 允許、使用者已見永久警告，且 Backend 以目前帳號密碼重新驗證成功時才可能執行。密碼正確不凌駕引用限制；禁止以 CASCADE 刪除歷史正式資料。

Repository 只執行 Service 已授權的 delete operation，不判斷刪除政策、不驗證密碼、不自行 commit。

## 14. 已確認的跨 Domain 資料規則

- Recipe 草稿允許 `quantity = 0`；任何可供 Requirement Calculation 使用的正式 Recipe 不得有 `quantity <= 0`，由 Service 驗證並由相應資料狀態/constraint 支援。
- Snapshot duplicate prevention 必須使用 Backend 產生的 deterministic fingerprint 與 PostgreSQL unique constraint；不得依賴 React state、Web session 或任何 Streamlit-style session state。fingerprint 精確組成於 Snapshot domain 實作時依業務規則確定。
- Snapshot 是 hard copy；建立後不受 ingredient、recipe、menu 或其他來源後續修改影響。
- `mL` 等 legacy unit 只在未來 Import/Migration 階段一次正規化，不建立永久 runtime compatibility。
- V1 正式資料 migration 延後至功能完成、回歸驗證與 migration rehearsal 階段；本階段不建立資料匯入工具。

## 15. 尚待 Domain 實作時確認的細節

目前五份文件沒有互相否定固定技術架構或主要業務流程。以下是不完整決策或需澄清的邊界，不應由實作者自行猜測：

以下細節不阻擋最小骨架，但不得在後續 domain 實作時自行猜測：

1. Access/Refresh Token 的有效期、refresh rotation、撤銷與 Web 安全儲存方式。
2. 哪些未被引用的主檔實際開放 Hard Delete，以及各 domain 的永久刪除 warning 文案。
3. Recipe 的草稿/正式狀態如何建模，以及從草稿轉正式的完整驗證時點。
4. Snapshot deterministic fingerprint 的精確欄位、排序/正規化方式與使用者明確重建策略。
5. `created_by`、`updated_by` 適用的「重要主表」逐表清單。
6. SQLite 現場資料的 migration、歷史 NULL/舊單位實況，留待 read-only audit。
7. V1 A/B 未列入 regression checklist 的微小 UI 差異。
8. 預設餐別的實際名稱集合。
9. 非七日菜單的「整週複製」邊界行為。

## 16. 架構變更程序

若未來確有需求偏離本文件：

1. 先記錄問題、選項、風險與決策。
2. 更新本文件或新增 ADR，再修改程式。
3. 同步更新 API contract、migration 與 tests。
4. 禁止以 temporary shortcut 跨過 Service / Repository，或在 React 重複 Backend 規則。
