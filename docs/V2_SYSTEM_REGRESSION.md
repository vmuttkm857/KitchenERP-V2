# KitchenERP V2 System Regression Matrix

> 狀態日期：2026-09-01。狀態定義：`PASS` 已有 API、UI 與自動測試；`PARTIAL` 核心可用但仍有操作或覆蓋缺口；`MISSING` 尚未實作；`INTENTIONALLY_CHANGED` V2 有意採不同流程。

| 分類 | V1 Feature / Business Rule | V2 Domain | API | Frontend Page | Automated Test | Manual Verification | Status |
|---|---|---|---|---|---|---|---|
| Auth | 個別帳號密碼登入、登出 | auth/users | `/auth/login`, `/auth/logout`, `/auth/refresh` | Login / App Shell | auth API/unit | Smoke 1, 16 | PASS |
| Auth | Access token 不落地、refresh rotation | auth | auth endpoints | AuthContext（記憶體） | auth flow/token tests | 重新整理與重新登入 | PASS |
| Auth | 管理員建立/修改/啟停/重設密碼、使用者自行改密碼 | users | `/users`, `/users/me/change-password` | Users / App Shell | users/audit API | Users manual acceptance | PASS |
| Auth | admin/user RBAC；Users/Audit/hard-delete 僅 admin | auth/users | role dependencies | admin-only system group | RBAC API/frontend targeted | 兩角色驗收 | PASS |
| Audit | 同交易 append-only before/after、actor snapshot、敏感資料清理 | audit | `/audit-logs` (GET only) | Audit Logs | audit/migration/query-budget tests | Audit manual acceptance | PASS |
| Master Data | 三類分類 CRUD、排序、啟停 | categories | `/categories/{kind}` | Categories | master data API | Smoke 2 | PASS |
| Master Data | 供應商 CRUD、啟停 | suppliers | `/suppliers` | Suppliers | master data API | Smoke 3 | PASS |
| Master Data | 供應商地址、全域排序與大型列表分頁 | suppliers | supplier list/reorder | Suppliers | supplier enhancement tests | 列表驗收 | PASS |
| Master Data | 食材、分類、供應商、價格歷史 | ingredients | `/ingredients`, price history | Ingredients | master data API | Smoke 4 | PASS |
| Nutrition | TFDA 官方食品 XLSX preview/confirm、重複匯入與新版未出現標記 | nutrition | `/nutrition/imports/*`, `/nutrition/foods` | Nutrition | importer/API/real-file validation | 2025 UPDATE1 XLSX | PASS |
| Nutrition | 手動食品 CRUD、停用／恢復及受引用 hard-delete 保護 | nutrition | `/nutrition/manual-foods/*` | Nutrition | nutrition API/audit tests | Manual food dialog | PASS |
| Nutrition | Ingredient 可對應官方／手動／未設定且不改 ERP 欄位 | nutrition/ingredients | `/ingredients/{id}/nutrition` | Ingredients | mapping transition/query-budget tests | Create/Edit mapping dialog | PASS |
| Nutrition | 每人配方營養即時計算；修正熱量禁止 partial，其他營養素各自判斷完整度 | nutrition/recipes | `/dishes/{id}/nutrition`, `/dishes/nutrition/bulk` | Dishes opt-in summary/detail | calculator/API/query-budget tests | Case A–G | PASS |
| Nutrition | g/kg/斤原生換算；NULL 與 0 分離，不套耗損或 TFDA 廢棄率 | nutrition/recipes | dish nutrition endpoints | Dishes detail | known-answer/unit tests | 不安全單位原因檢視 | PASS |
| Nutrition | Ingredient 專屬營養重量換算；非重量與 ml/L 只接受 explicit grams，不影響採購／需求／備料／成本 | nutrition/ingredients | `/ingredients/{id}/nutrition-unit-conversions` | Ingredients conversion dialog | CRUD/validation/live calculation regressions | 1 隻=180g、20ml×1.15g | PASS |
| Nutrition | Detailed export 動態輸出全部 reportable numeric nutrients；Excel 原生超寬、PDF 每 7 項分頁 | exports/nutrition | menu export `nutrition=detailed` | Menu Export Dialog | 105-column Excel / multi-page PDF tests | E5300104 全營養素抽查 | PASS |
| Master Data | 主檔 hard delete 需密碼且受引用限制 | categories/suppliers/ingredients/dishes/menus | `hard-delete` commands | 各主檔 danger flow | master data/menu API | 以測試資料確認拒絕條件 | PASS |
| Master Data | 搜尋、狀態篩選、SQL 分頁 | master data | list endpoints | 各列表 | API pagination tests | 列表工具列 | PARTIAL |
| Recipe | 菜色 CRUD、分類、啟停 | dishes | `/dishes` | Dishes | dishes API | Smoke 5 | PASS |
| Recipe | 多食材配方、數量、單位、耗損、排序 | recipes | `/dishes/{id}/recipe` | Recipe Editor | recipe/API/unit | Smoke 6 | PASS |
| Recipe | g/kg/斤、ml/L；不跨 dimension | shared/recipes | recipe + calculation | Recipe/Kitchen/Requirements | quantity and calculation unit tests | Smoke 9–10 | PASS |
| Recipe | 草稿可為 0，需求計算阻擋非正數 | recipes/requirements | recipe/requirements | Recipe/Requirements | regression/unit | 顯示異常 | PASS |
| Menu | 菜單 CRUD、分類、日期驗證、啟停 | menus | `/menus` | Menus | menu API | Smoke 7 | PASS |
| Menu | 動態餐別新增、排序、啟停 | menus | meal-type endpoints | Menu Editor「餐別設定」 | menu API | Smoke 8 | PASS |
| Menu | 日期 × 餐別矩陣、餐格批次交易 | menus | `/menus/{id}/editor` | Menu Editor | menu API | Smoke 8 | PASS |
| Menu | 餐格平時摘要，集中編輯菜色、人數、備註、排序 | menus | editor aggregate | Menu Editor panel | TypeScript build + menu API | Smoke 8 | PASS |
| Menu | 單日／完整七日加入或覆蓋複製 | menus | `copy-day`, `copy-week` | 「複製菜單」panel | menu API transaction tests | 覆蓋確認 | PASS |
| Menu | 餐別合併／菜色分格／漂亮公告七日週表；單張 A4 Excel、4 張拼接 Excel（公告版除外）與 image-only PDF | exports | `/exports/menus/{id}/{layout}/{format}?variant=single\|poster` | Menu Editor Export Dialog | export unit/API/frontend tests | Excel COM 1/4-page and PDF raster review | PASS |
| Menu | Opt-in 熱量版與原版＋熱量版＋詳細營養輸出；相同 Dish 明細只列一次 | exports/nutrition | menu export `nutrition=none\|calories\|detailed` | Menu Export Dialog | Excel/PDF/API/frontend regression | Nutrition export review | PASS |
| Kitchen | 依日期、餐別、菜色產生只讀備料 | kitchen_operations | `/kitchen-operations/calculate` | Kitchen Operations | kitchen API/unit | Smoke 9 | PASS |
| Kitchen | 菜色／食材／供應商三種 view | kitchen_operations | 同一 aggregate API | Kitchen Operations toggles | kitchen API | 切換不重新計算 | PASS |
| Kitchen | 備料量 = 人數 × 配方量 × (1+耗損) | kitchen_operations/shared | calculate | Kitchen Operations | known-answer tests | Smoke 9 | PASS |
| Kitchen | Excel/PDF/A4 現場列印，文字公式注入防護 | exports | `/exports/kitchen-operations/*`, `/a4-xlsx` | Header actions | export API/unit/A4 layout | 列印預覽與實體 A4 | PASS |
| Kitchen | 七日週配料表，依菜色顯示人數、食材與安全換算量；異常不靜默省略 | exports/kitchen_operations | `/exports/kitchen-operations/simple/{format}?variant=single\|poster` | Kitchen Export Dialog | known-answer/conversion/anomaly/image-only tests | Excel COM 1/4-page and PDF raster review | PASS |
| Requirement | 多菜單與日期 criteria、Decimal 彙總 | requirements | `/requirements/calculate` | Requirements | requirement API/unit | Smoke 10 | PASS |
| Requirement | 總表／供應商分組、集中異常 | requirements | aggregate result | Requirements | requirement API | Smoke 10 | PASS |
| Requirement | 日期 overlap／關鍵字候選、server-side pagination、保留已選菜單 | requirements/menus | `/menus` filters | Requirements candidate selector | frontend/menu API | 候選操作 | PASS |
| Requirement | 每日需求／依供應商／總需求及來源菜單 attribution | requirements | result 含 daily rows | 三種 result view | calculator/export/frontend tests | 明細切換 | PASS |
| Snapshot | 建立 immutable-like hard copy、revision、duplicate fingerprint | snapshots | `/requirement-snapshots` | Snapshots | snapshot API/concurrency | Smoke 11 | PASS |
| Snapshot | 調整採購量／單位且不回寫來源 | snapshots | item PATCH | Snapshot Detail | snapshot/purchase tests | Smoke 12 | PASS |
| Snapshot | 建採購後鎖定；未建採購可控 hard delete | snapshots | detail/delete | Snapshot Detail | snapshot/purchase tests | Smoke 13 | PASS |
| Purchase | Snapshot 一對一正式 batch、按供應商拆單 | purchases | `/purchases` | Purchases | purchase API/concurrency | Smoke 13 | PASS |
| Purchase | draft confirm/cancel；confirmed 可取消；cancelled readonly | purchases | transition endpoints | Purchase Detail | purchase API | Smoke 14 | PASS |
| Purchase | 正式資料 hard copy、成本與 Decimal | purchases | detail | Purchase Detail | full workflow/purchase tests | Smoke 14 | PASS |
| Purchase | 配送 allocation、拆分、日期與上限 | purchases/delivery | — | — | — | — | MISSING |
| Purchase | 結案／恢復與正式單刪除 | purchases | — | — | — | — | MISSING |
| Export | Requirements Excel | exports | `/exports/requirements/xlsx` | Requirements | export/full workflow | Smoke 15 | PASS |
| Export | Snapshot Excel | exports | `/exports/requirement-snapshots/{id}/xlsx` | Snapshots | export/full workflow | Smoke 15 | PASS |
| Export | Purchase Excel/PDF、多供應商 | exports | `/exports/purchases/{id}/*` | Purchases | export/full workflow | Smoke 15 | PASS |
| Technical | PostgreSQL only、Alembic 0011 | db/migrations | — | — | base→head migration | `alembic current` | PASS |
| Technical | API→Service→Repository、request Session/process Engine | all | all | — | full suite/integration | — | PASS |
| Technical | Query budgets、無逐列 detail fetch | repositories/frontend | aggregate endpoints | all pages | domain query-budget tests | Network smoke | PASS |
| V1 change | Streamlit rerun/session-state 流程 | all | versioned API | React local state | regression suite | normal navigation | INTENTIONALLY_CHANGED |
| V1 change | SQLite 與 runtime `mL` compatibility | db/shared | — | — | PostgreSQL guard | — | INTENTIONALLY_CHANGED |

## INTENTIONALLY_CHANGED 原因

- Streamlit rerun/session state 改為 React client state + versioned Backend API，避免整頁 rerun、重複查詢與 UI session 作為一致性保證。
- SQLite 不再支援；PostgreSQL 是唯一正式與測試資料庫。
- V1 資料已確認全為測試資料，不會匯入 V2；`mL` 舊資料只作 regression 參考，不建立 runtime compatibility layer。
- Snapshot duplicate protection 改為 deterministic fingerprint + PostgreSQL unique constraint，不依賴單一 UI session。

## V1 Missing Feature Audit

### A. 正式使用前必須補

- 全新 PostgreSQL production database bootstrap、migration-to-head 與初始 admin 驗證。
- 正式環境部署、HTTPS、production secrets、備份／還原演練與操作手冊。
- 若現場每日工作依賴配送：delivery allocations、配送日期、拆分／改量與訂購量上限。
- 以實際使用者完成本文件及 `MANUAL_SMOKE_TEST.md` 的驗收與資料格式確認。

### B. 可以之後補

- Requirement 更進階的多分類候選篩選（日期 overlap、關鍵字與每日明細已完成）。
- 每日叫貨表、帳務明細、分帳與進階供應商／日期報表。
- Purchase 結案／恢復與受控正式單刪除（需先確認新 V2 lifecycle）。
- 複雜列表的直接頁碼跳轉與更完整 filters。

### C. 已被新版流程取代

- Streamlit session-state 防重、widget key 與整頁 rerun。
- Frontend/畫面直接查 DB、每列即時補查。
- SQLite connection workaround。
- 「先產生再下載」的暫存匯出流程；V2 由 authenticated API 直接下載。

### D. 不再需要

- SQLite compatibility layer。
- Business rules 在 UI 與 Backend 各保存一份。
- 舊 `mL` 永久 runtime 相容分支。
- Kubernetes、microservices、Redis 等不符合 3–5 人規模的基礎設施。
