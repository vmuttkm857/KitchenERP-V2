# KitchenERP V2 開發計畫

> 目前狀態：**Phase 5－Menus 已完成**。下一階段必須等待明確指示才可開始。每一階段都必須遵守根目錄 `ARCHITECTURE.md`，並以 `docs/V2_REGRESSION_REQUIREMENTS.md` 作回歸基準。

## Phase 0：架構與核心決策（已完成）

- 已固定 Access Token + Refresh Token、`admin/user`、重要主表預留 actor 欄位但不建完整 audit log。
- 已固定 Decimal string API、UTC timestamp / Asia-Taipei 顯示、三類 Delete Policy、recipe 草稿 0 / 正式 >0、Snapshot fingerprint + DB unique constraint。
- 已固定 `menu_days.menu_meal_type_id` FK、`dish_categories.sort_order` 與 legacy unit 只在 migration 階段正規化。
- 對 V1 現場資料做另行 read-only audit，產出資料遷移風險清單。
- Token 細節、Snapshot fingerprint 組成、預設餐別與非七日週複製留待對應 domain 實作前確認。

完成條件：所有會影響 schema 或 API contract 的決策已有紀錄；未決事項有明確 owner，且不阻擋下一階段基礎建設。

## Phase 1：工程骨架與品質門檻（已完成）

- 建立 React + TypeScript 與 FastAPI 專案骨架。
- 建立 PostgreSQL-only SQLAlchemy 2.x、Alembic、request-scoped Unit of Work。
- 建立 pytest 分層、PostgreSQL integration test、migration-from-empty test。
- 建立最小 health endpoint、環境設定、統一 error/telemetry 擴充位置與 OpenAPI 基礎。
- 本輪不建立 ERP tables、完整 Authentication、CI 或 V1 data migration。

完成條件：空 schema 可由 Alembic 建立；健康檢查、測試與 query telemetry 可運作；尚無 ERP domain 功能。

## Phase 2：Authentication 與 Users（已完成）

- users schema、password hashing、登入/登出/refresh 或 session lifecycle。
- Backend authorization enforcement 與前端登入/route guard。
- 依 Phase 0 決策加入角色與必要 audit actor。

完成條件：每位使用者以獨立帳密登入；停用、權限與安全回歸測試通過。

## Phase 3：基礎主檔（已完成）

依序實作：

1. categories（食材、菜色、菜單分類）
2. suppliers
3. ingredients + ingredient price history

重點：server-side 搜尋/篩選/分頁、停用保留引用、食材與初始價格/改價歷史的原子交易。

## Phase 4：菜色與標準配方（已完成）

依序實作：

1. dishes
2. shared unit/quantity/money primitives
3. recipes batch commands、單位換算、耗損與單份成本

重點：Decimal、不可換算即待確認、同菜色食材唯一、批次 rollback、lazy preview 與 query budget。

## Phase 5：菜單與週排餐（已完成）

- menus、動態餐別、日期餐格 lazy materialization。
- 餐格 basket、批次加菜、人數、備註、連續排序。
- 一日/整週加入與覆蓋複製。
- 週菜單可編輯版與列印版 Excel。

重點：aggregate API、真正 ID、單一 transaction、避免每格/每列 N+1。

## Phase 6：廚房作業／備料

- 單餐、單日、整張菜單三種範圍。
- 依菜色、食材、供應商 view。
- 缺配方/缺食材/不可換算警示。
- A4 備料 Excel 與整週總覽。

重點：只讀菜單與配方，不讀採購量；Web 與 Excel 共用 Backend quantity formatter/輸出規則。

## Phase 7：食材需求

- 多分類/菜單/日期候選與快速加入。
- requirement preview、彙總/明細、成本及待確認警示。
- 保留 menu/date schedule，不跨菜單錯誤合併。

重點：純計算先做 unit tests，再接 Repository aggregate query 與 API query budget。

## Phase 8：需求快照與需求確認

- snapshot、items、schedules hard copy 的原子建立。
- 防重複策略、狀態查詢、人工採購量/單位調整。
- 未建採購單可刪、已建單禁止刪除。

重點：不可回寫原需求/菜單/配方/食材；歷史資料不受主檔變更影響。

## Phase 9：正式採購與配送

- 從 snapshot 原子建立 purchase order/items/allocations。
- 工作匣、每日叫貨、配送拆分/改期/改量/刪除。
- ordered quantity 上限、結案/恢復/刪除與各類 Excel。

重點：正式採購是第二層 hard copy；不修改或刪除來源 snapshot。

## Phase 10：V1 資料遷移與完整回歸

- 依 read-only audit 結果建立一次性、可重跑或有 checkpoint 的 migration 工具與 reconciliation report。
- 正規化舊型別/單位，保存 hard-copy 與 source identity。
- 完成 regression checklist、query budgets、代表性資料量效能、安全與備份/復原驗證。
- 進行使用者驗收、平行驗證與 cutover/rollback 演練。

完成條件：`V2_REGRESSION_REQUIREMENTS.md` 已逐項有證據；V1/V2 重要 totals 與歷史抽查一致；效能明顯優於 V1 且沒有 N+1/connection leak。

## 每個 Phase 的共同 Definition of Done

- API → Service → Repository 分層未被繞過。
- schema 變更有 Alembic migration，且 PostgreSQL integration test 通過。
- 核心 business rule 有 unit/regression test；批次交易有中途失敗 rollback test。
- OpenAPI contract、前端 client type 與文件同步。
- 列表採 server-side filter/pagination；主要 endpoint 符合 query budget。
- error 不洩露 SQL、parameters、token、密碼或 database URL。
- 沒有新增 SQLite、microservice、Kubernetes 或未證明必要的 Redis。
