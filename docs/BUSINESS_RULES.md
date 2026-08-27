# KitchenERP V1 業務規則

> 規則來源為 B 的業務邏輯與 A 的 active code 交叉核對。A/B 不同且無法證明為有意需求變更者標示「待確認」。V2 建議保留的是規則語意，不是舊 Streamlit 或 SQLite 實作。

## 1. 主檔與識別規則

| 規則 | 輸入 → 判斷/計算 → 輸出 | 邊界與防呆 | 來源 | A/B / V2 |
|---|---|---|---|---|
| 食材分類 | 分類名稱 → 不可空白且唯一 → 分類主檔 | 停用不改既有食材關聯 | `modules/category/page.py` | 相同；保留 |
| 菜色分類 | 分類名稱、啟用、排序呈現 → `dish_category_id` → 菜色可選分類 | 菜色未分類合法（NULL） | `category/page.py`, `dish/page.py` | 相同；保留 |
| 供應商 | 供應商代碼不可空、唯一；名稱不可空 → 供應商主檔 | 停用後仍保留既有歷史/食材 reference | `supplier/page.py` | 相同；保留 |
| 食材 | 代碼唯一、名稱、分類（必填）、基本單位（必填）、單價、可選主供應商 | 基本單位是食材主檔單位；供應商可為 NULL | `ingredient/page.py` | 相同；保留 |
| 菜色 | `dish_code`、`dish_name` 均唯一；分類可 NULL；可啟停 | 不能把 UNIQUE/FK/CHECK 一律誤報成同一錯誤 | `dish/page.py` | A 強化錯誤分類；保留 |

## 2. 價格與食材主檔

### R-PRICE-01：建立初始價格歷史
- **輸入**：新食材的目前單價、基本單位、主要供應商與生效日。
- **規則**：同一交易先新增 `ingredients`，再新增 `ingredient_price_history`；任何一步失敗必須 rollback。
- **輸出**：食材主檔與首筆價格歷史同時存在，或都不存在。
- **來源**：`modules/ingredient/page.py:add_ingredient`（名稱以實際函式為準；新增 UI 呼叫此流程）。
- **A/B**：規則相同；A 針對 PostgreSQL `RETURNING`、DATE、NUMERIC 補兼容。
- **V2**：保留，並以單一 application transaction 實作。

### R-PRICE-02：改目前單價即追加歷史
- **輸入**：食材編輯後的單價與價格資訊。
- **規則**：更新 `ingredients.current_price` 時，同一交易 INSERT 一筆價格歷史；不是覆蓋歷史。
- **邊界**：失敗不可留下「主檔已改、歷史未寫」的半完成資料。
- **來源**：`modules/ingredient/page.py:update_ingredient`。
- **V2**：保留。

## 3. 配方、單位與成本

### R-RECIPE-01：配方引用食材，不複製供應商
- **輸入**：`dish_id`、`ingredient_id`、每人用量、配方單位、耗損率、備註。
- **規則**：`dish_ingredients` 只引用 ingredient。左側顯示的供應商以 `ingredients.primary_supplier_id → suppliers` 取得。
- **輸出**：食材換供應商後，配方不需要改；顯示自動反映主檔。
- **來源**：`dish/page.py:get_dish_ingredients`, `get_recipe_dialog_recipe`。
- **V2**：保留。

### R-RECIPE-02：同菜色不得重複食材
- **判斷**：`UNIQUE(dish_id, ingredient_id)`，UI 與批次服務都先檢查。
- **防呆**：同批傳入重複 ID、已存在配方、停用/不存在食材，均拒絕；批次不留部分新增。
- **來源**：`dish/page.py:add_dish_ingredients_batch`、schema unique constraint。
- **V2**：保留 DB constraint 及 service validation。

### R-RECIPE-03：配方使用單位與食材基本單位分離
- **輸入**：食材基本單位 `ingredients.unit`；配方單位 `dish_ingredients.unit`。
- **規則**：兩者可不同，例如食材基本單位「斤」、配方「g」。不可因建立配方而改食材基本單位。
- **來源**：`dish/page.py:RECIPE_UNIT_OPTIONS`, recipe editor, `requirement/page.py:build_summary`。
- **A/B**：兩版均有此欄位語意；A 的 PostgreSQL NUMERIC 支援不改規則。
- **V2**：必須保留。

### R-RECIPE-04：單位換算
- **安全可換算重量**：`g ↔ kg ↔ 斤`，其中 `1 斤 = 600 g`。
- **容量相容**：`ml ↔ L`；舊資料 `mL` 等同 `ml`。
- **不可換算**：片、個、隻、包、盒等計數單位與重量/容量跨類別，或任何未定義組合，回傳不可換算（不是猜測）。
- **來源**：`modules/common/quantity.py:normalize_unit`, `convert_quantity`; 菜色模組也有相同歷史實作。
- **重複實作**：`dish/page.py:convert_quantity` 與 `common/quantity.py:convert_quantity`。V2 應只留一個 domain converter。
- **V2**：保留換算語意及「不猜測」原則。

### R-RECIPE-05：耗損與單份成本
- **計算**：`含耗損量 = 每人用量 × (1 + loss_rate / 100)`。
- **成本**：將含耗損配方量換為食材基本單位後，`成本 = 換算量 × current_price`。
- **輸出**：所有食材都可換算才顯示完整單份標準成本；任一不可換算則警示，不虛構成本。
- **邊界**：quantity/loss_rate 不得為負數；目前 UI 對新配方量常要求正值，但 schema 允許 quantity=0，供批次先加後編輯流程使用。
- **來源**：`dish/page.py:_apply_loss_rate`, `calculate_ingredient_cost`, `render_recipe_cost_summary`；schema CHECK。
- **V2**：保留。quantity=0 是否在正式儲存一律禁止屬 **待確認**，需由產品決定。

## 4. 菜單與週排餐

### R-MENU-01：日期區間
- **規則**：菜單有 `menu_start_date` 與 `menu_end_date`，區間包含兩端；結束日不能早於開始日。
- **來源**：`menu/page.py:add_menu`, `initialize_menu_days`; PostgreSQL schema `chk_menus_date_range`。
- **V2**：保留。

### R-MENU-02：餐別是每張菜單的動態設定
- **輸入**：餐別名稱、排序、啟用狀態。
- **規則**：同一菜單的餐別名稱唯一；預設餐別只在該菜單尚無餐別時建立。可排序、停用及重新啟用。
- **輸出**：週矩陣依啟用餐別及 `sort_order` 顯示；歷史已存在餐別資料不因停用而刪除。
- **來源**：`menu/page.py:get_menu_meal_types`, `add_menu_meal_type`, `initialize_default_meal_types`, `show_meal_type_settings`。
- **V2**：保留。

### R-MENU-03：菜單日期×餐別格
- **規則**：`menu_days` 的 identity 為 `(menu_id, menu_date, meal_type)`；必要時在加菜前才 ensure 建立，純查看空格不寫 DB。
- **來源**：`menu/page.py:ensure_menu_day`, `get_menu_day_id`, schema unique。
- **V2**：保留 lazy materialization 或等效語意。

### R-MENU-04：餐格菜色與順序
- **輸入**：menu day、dish、人數、備註、排序。
- **規則**：同一餐格不能重複 dish；初始加菜排在最後。上/下移只交換相鄰兩筆；直接輸入排序、批刪後，結果必須重整為連續 `1..N`。
- **資料身份**：一律 `menu_dish_id`，不可用顯示列 index 或菜名。
- **來源**：`menu/page.py:add_menu_dish`, `reorder_menu_dish`, `delete_menu_dish`, `save_menu_dish_management_changes`, `delete_menu_dishes_batch`。
- **V2**：保留。

### R-MENU-05：加菜 basket
- **規則**：每個 `(menu_day_id, menu_meal_type_id)` 餐格有獨立、輕量的待加入 basket；跨搜尋、分類、分頁不清除；真正寫入只在「加入選取菜色」。
- **防呆**：以 `dish_id` 去重并拒絕已在該餐格的菜色；批量寫入一筆失敗時整批 rollback。
- **來源**：`menu/page.py:get_meal_slot_basket`, `add_menu_dishes_batch`, `render_add_dishes_workspace` / active dialog。
- **V2**：保留行為；前端儲存形式可重設計。

### R-MENU-06：複製一天與整週
- **一天**：來源/目的日期可跨菜單；餐別按名稱對應。加入模式保留目的資料並跳過同一 `(日期, 餐別, dish)`；覆蓋模式先二次確認，再清目的日期的菜色後複製。
- **整週**：來源與目的的完整日期區間；先驗證目的菜單具有來源使用餐別；單一 transaction 寫入完整七日，任一天錯誤整週 rollback。
- **複製內容**：`dish_id`、`diner_count`、`notes`、`sort_order`。
- **來源**：`menu/page.py:copy_menu_day`, `copy_menu_week`, copy Dialog。
- **V2**：保留。

## 5. 食材需求與快照

### R-REQ-01：需求候選與日期
- **規則**：候選菜單可按期間、名稱、複數 menu category 篩選；候選最多 100 筆。已選 menu ID 即使已不在目前候選仍要補回，避免分類/搜尋改變時遺失。
- **快速加入**：對每個選定日期，找 `menu_start_date <= date AND menu_end_date >= date` 的所有菜單，合併 ID 且去重；不受目前搜尋/分類限制。
- **來源**：`requirement/page.py:get_menus`, `get_menus_by_ids`, `get_menu_ids_for_requirement_dates`, `add_all_menus_for_quick_dates`。
- **V2**：保留。

### R-REQ-02：系統需求量
- **逐配方列**：`raw = quantity_per_person × diner_count`；`required = raw × (1 + loss_rate/100)`。
- **換算**：能換到 ingredient basic unit 就以基本單位彙總；不能換則保留 recipe unit 並 `needs_review=True`。
- **彙總 key**：`(ingredient_id, final_unit)`；日期需求 key：`(menu_id, ingredient_id, final_unit, menu_date)`，**不跨菜單合併日程**。
- **採購初值**：可換算時 `建議採購量 = 需求量`，不在需求階段做包裝、最小量、進位；不可換算時採購量與估算成本為空。
- **成本**：`需求量 × 食材目前單價`，僅限可換算。
- **來源**：`requirement/page.py:build_summary`, `build_date_requirements`。
- **V2**：保留。

### R-REQ-03：缺配方/缺食材資料
- **規則**：菜單中的菜色沒有配方，不納入需求計算但列 warning；配方食材主檔不存在也不硬算。
- **來源**：`requirement/page.py:get_dishes_without_recipe`, `show_missing_recipe_warning`; `kitchen_work/page.py:build_preparation_rows`。
- **V2**：保留。

### R-SNAPSHOT-01：需求快照是 hard copy
- **規則**：確認需求時寫入 snapshot 本體、每項 hard-copy、逐日 schedule；快照不依賴之後菜單/食材/供應商/價格的變動。
- **包含**：目標菜單與日期 JSON、總成本、食材/供應商文字、需求/採購初始量、單價、單位、包裝/最小量、需確認旗標、menu/date schedule。
- **交易**：snapshot、items、schedules 同一 transaction；任一步失敗 rollback。
- **防重複**：同 Streamlit session 的同一計算 signature 不可重複儲存。
- **來源**：`requirement/page.py:snapshot_signature`, `save_requirement_snapshot`。
- **V2**：保留 hard copy 與原子性。signature 的「僅 session 防重」是否足夠是 **待確認**。

### R-SNAPSHOT-02：人工調整只改快照採購欄位
- **規則**：可調 `adjusted_quantity` 與 `purchase_unit`；不回寫原始 required quantity、菜單、配方或食材主檔。
- **換算**：重量單位可在 `g/kg/斤` 中切換；其他類別只能保留系統單位。若只改單位且數量未改，需安全換算數量。
- **成本**：以調整數量換回系統單位後，乘 snapshot hard-copy 單價。
- **來源**：`requirement_snapshot/page.py:allowed_purchase_units`, `normalize_adjustment_for_save`, `adjusted_cost`, `save_adjustments`。
- **V2**：保留。

### R-SNAPSHOT-03：快照生命週期
- **狀態判定**：不是 snapshot 欄位；`purchase_orders.source_snapshot_id` 存在即「已建立叫貨單」，不存在即「待建立」。
- **刪除**：只可刪未建正式叫貨單的 snapshot；已建單者禁止，以保留採購歷史。刪除時子項目/日程連動移除。
- **來源**：`requirement_snapshot/page.py:get_snapshots`, `delete_snapshot_without_purchase_order`。
- **V2**：保留。

## 6. 正式採購與配送

### R-PO-01：建立正式採購單是快照的第二層 hard copy
- **規則**：從 requirement snapshot 建立 `purchase_orders`、`purchase_order_items`、`purchase_order_allocations`；保留 source snapshot ID/名稱及 item/schedule ID 作追蹤，但採購內容不應被後續主檔變動改寫。
- **輸入**：snapshot、名稱、備註；item 的 snapshot adjusted quantity 為正式訂購初值來源。
- **交易**：主檔、items、allocations 一次完成，失敗無半張單。
- **來源**：`purchase/page.py:create_purchase_order`。
- **V2**：保留。

### R-PO-02：每日叫貨與配送
- **規則**：正式 `ordered_quantity` 是上限；配送 allocation 的換算後合計不得超過該品項 ordered quantity。可新增、改日期/量、刪除或建立額外 delivery allocation。
- **日期**：`requirement_date` 是需求 hard copy；修改 delivery date 不可改 requirement date。
- **來源**：`purchase/page.py:save_delivery_allocations`, `add_delivery_allocation`。
- **V2**：保留。

### R-PO-03：結案與恢復
- **規則**：結案只更新 purchase order status/closed time，保留所有每日叫貨與配送歷史；已結案單不可改配送，需先恢復。恢復仍是同一張單，非複製。
- **來源**：`purchase/page.py:close_purchase_order`, `reopen_purchase_order`, UI guards。
- **V2**：保留。

### R-PO-04：刪除正式採購單
- **規則**：刪除 order，items/allocations 連動移除；**不刪來源 requirement snapshot**。
- **來源**：`purchase/page.py:delete_purchase_order`、schema cascade。
- **V2**：保留，並保留 UI 二次確認。

## 7. 廚房備料與列印

### R-KITCHEN-01：備料使用需求公式，不使用採購量
- **計算**：與 R-REQ-02 相同：配方量 × 該餐格用餐人數 ×（1+耗損）。
- **明確排除**：不使用 package size、minimum order、purchase order、actual delivery 或人工叫貨量。
- **範圍**：單餐、單日、整張菜單；可按菜色、食材或供應商重組。
- **來源**：`kitchen_work/page.py:get_preparation_rows`, `build_preparation_rows`, `aggregate_preparation_rows`。
- **V2**：保留。

### R-KITCHEN-02：備料顯示格式
- **規則**：顯示時，整數不帶小數；非整數最多兩位並去尾零。自動易讀模式將 `g >= 1000` 顯示為 kg、`ml >= 1000` 顯示為 L；原始模式不轉單位。
- **安全**：只格式化最後顯示值，不改底層 quantity/Decimal；不可換算列照樣顯示待確認。
- **來源**：`kitchen_work/page.py:format_preparation_quantity`, `render_quantity`。
- **V2**：保留。

### R-KITCHEN-03：列印 Excel
- **規則**：A4 直式、每頁重複完整頁首與欄表頭；正常菜色區塊不可被跨頁拆開，超大單一道菜才允許「續」。文字需防 Excel formula injection。
- **來源**：`kitchen_work/page.py:build_preparation_excel_bytes`, `paginate_preparation_slot`, `safe_excel_text`。
- **A/B**：B 有 Excel builder；A 有後續頁首/分頁/顯示格式修正。V2 應以 A 的觀察行為驗收。

## 8. V2 規則設計提醒

1. 金額與量一律 domain Decimal；只在 UI/API/Excel 最後轉字串或明確浮點。
2. 將單位換算、需求量與成本計算集中在 domain service，避免 `dish`、`requirement`、`snapshot` 各自複製。
3. DB constraint 是最後防線；service validation 是可讀錯誤訊息與跨資料表規則的防線。
4. 對「待確認單位」維持保守：禁止估算成本/包裝換算，不自動猜單位。
