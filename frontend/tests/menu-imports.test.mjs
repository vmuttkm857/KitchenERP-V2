import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {menuImportDates,menuImportGridRows,menuImportStatus} from '../src/features/menus/menuImportGrid.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const dialog=read('../src/features/menus/MenuImportDialog.tsx')
const review=read('../src/features/menus/MenuImportReviewPage.tsx')
const grid=read('../src/features/menus/MenuImportWeekGrid.tsx')
const menus=read('../src/features/menus/MenusPage.tsx')
const app=read('../src/app/App.tsx')
const picker=read('../src/features/menus/DishSearchPicker.tsx')
const css=read('../src/styles/global.css')
const line=(date,meal,mealOrder,column,columnOrder,name,reviewRequired=false)=>({
  line_key:`${date}-${meal}-${column}`,date,meal_name:meal,meal_sort_order:mealOrder,column_name:column,column_sort_order:columnOrder,
  original_import_name:name,normalized_name:name,dish:reviewRequired?null:{id:name,code:name,name,is_active:true},status:reviewRequired?'UNMATCHED':'MATCHED',review_required:reviewRequired,source_row:2,source_column:3,diner_count:1,
})

test('weekly planner uses the imported date range and backend meal/column sort order',()=>{
  const dates=menuImportDates('2026-10-05','2026-10-11')
  assert.equal(dates.length,7)
  const rows=menuImportGridRows([
    line('2026-10-06','午餐',2,'副菜',2,'B'),line('2026-10-05','早餐',1,'主菜',1,'A'),line('2026-10-05','午餐',2,'主菜',1,'C'),
  ],dates)
  assert.deepEqual(rows.map(row=>`${row.mealName}/${row.columnName}`),['早餐/主菜','午餐/主菜','午餐/副菜'])
  assert.equal(rows[1].cells[0]?.original_import_name,'C')
  assert.equal(rows[2].cells[1]?.original_import_name,'B')
})

test('layout metadata preserves configured rows that are blank for all seven days',()=>{
  const dates=menuImportDates('2026-10-05','2026-10-11')
  const layout=[
    {meal_name:'午餐',meal_sort_order:1,column_name:'主菜',column_sort_order:1},
    {meal_name:'午餐',meal_sort_order:1,column_name:'備菜3',column_sort_order:2},
  ]
  const rows=menuImportGridRows([line('2026-10-05','午餐',1,'主菜',1,'A')],dates,layout)
  assert.deepEqual(rows.map(row=>row.columnName),['主菜','備菜3'])
  assert.equal(rows[1].cells.every(cell=>cell===null),true)
})

test('upload is explicit xlsx preview then creates the draft from the same file and hash',()=>{
  assert.match(menus,/匯入 Excel/)
  assert.match(dialog,/accept="\.xlsx/)
  assert.match(dialog,/解析預覽/)
  assert.match(dialog,/\/menu-imports\/preview/)
  assert.match(dialog,/expected_source_hash/)
  assert.match(dialog,/preview\.source_hash/)
  assert.match(dialog,/建立匯入草稿/)
  assert.match(dialog,/preview\.layout/)
  assert.doesNotMatch(dialog,/preview\.lines.*JSON\.stringify/s)
})

test('preview exposes summary fatal overlap and review-required cells without mutating a menu',()=>{
  for(const text of ['需確認','日期與既有菜單重疊','無法建立草稿','建立匯入草稿'])assert.match(dialog,new RegExp(text))
  assert.match(grid,/if\(line\.review_required\)return'needs-review'/)
  assert.match(css,/\.menu-import-cell\.needs-review\{background:#fff1f2/)
  assert.doesNotMatch(dialog,/\/menus\/[^'`]*editor/)
})

test('duplicate draft and unfinished list both navigate to persistent review',()=>{
  assert.match(dialog,/MENU_IMPORT_DRAFT_EXISTS/)
  assert.match(dialog,/existing_batch_id/)
  assert.match(dialog,/繼續原草稿/)
  assert.match(dialog,/未完成的 Excel 匯入/)
  assert.match(app,/menu-import-review/)
  assert.match(app,/MenuImportReviewPage/)
})

test('review is restored only from batch GET and line resolution refetches authoritative detail',()=>{
  assert.match(review,/apiRequest<MenuImportBatchDetail>\(`\/menu-imports\/\$\{batchId\}`\)/)
  assert.match(review,/method:'PATCH'/)
  assert.match(review,/dish_id:selected\.id/)
  assert.match(review,/await apiRequest\(path,init\);onResolved\(await apiRequest<MenuImportBatchDetail>/)
  assert.doesNotMatch(review,/setDetail\([^)]*review_required:\s*false/)
  assert.match(review,/菜單審核完成/)
  assert.match(review,/可以建立新的正式菜單/)
})

test('ready draft finalizes into a new menu and opens the existing menu editor',()=>{
  assert.match(review,/detail\.can_finalize&&<button[^>]*onClick=\{\(\)=>setFinalizeOpen\(true\)\}[^>]*>建立正式菜單/)
  assert.match(review,/defaultMenuName\(batch\.original_filename\)/)
  assert.match(review,/Excel 檔案/)
  assert.match(review,/已排除/)
  assert.match(review,/\/categories\/menu\?active=true&page_size=100/)
  assert.match(review,/start_date:batch\.start_date,end_date:batch\.end_date/)
  assert.match(review,/日期重疊僅供參考，不會覆蓋既有菜單/)
  assert.match(review,/不會修改或覆蓋其他既有菜單/)
  assert.match(review,/`\/menu-imports\/\$\{batch\.id\}\/finalize`/)
  assert.match(review,/method:'POST'/)
  assert.match(review,/category_id:categoryId\|\|null/)
  assert.match(review,/onOpenMenu\(result\.menu\)/)
  assert.match(review,/event\.key==='Escape'/)
  assert.match(review,/saving\|\|loadingInfo\|\|!name\.trim\(\)/)
  assert.match(review,/MENU_IMPORT_NOT_READY/)
  assert.match(app,/onOpenMenu=\{menu=>\{setEditingMenu\(menu\);navigate\('menu-editor'\)\}\}/)
})

test('finalized import history is read-only and can reopen its formal menu',()=>{
  assert.match(review,/detail\.status==='FINALIZED'/)
  assert.match(review,/onLine=\{finalized\?undefined:openReview\}/)
  assert.match(review,/!finalized&&<button[^>]*className="danger"/)
  assert.match(review,/已建立正式菜單/)
  assert.match(review,/匯入紀錄已鎖定/)
  assert.match(review,/apiRequest<Menu>\(`\/menus\/\$\{menuId\}`\)/)
  assert.match(css,/\.status-finalized/)
  assert.match(css,/\.menu-import-finalized-banner/)
})

test('dish correction reuses active paged dish search and keeps inactive candidates unavailable',()=>{
  assert.match(review,/active:'true'/)
  assert.match(review,/page_size:'20'/)
  assert.match(review,/DishSearchPicker/)
  assert.match(picker,/categories\.filter\(item => item\.is_active\)/)
  assert.match(review,/搜尋並選擇現有菜色/)
  assert.match(review,/草稿尚未變更/)
})

test('delete requires a dedicated confirmation and returns to menu management only on success',()=>{
  assert.match(review,/刪除匯入草稿/)
  assert.match(review,/確認刪除草稿/)
  assert.match(review,/method:'DELETE'/)
  assert.match(review,/await apiRequest\(`\/menu-imports\/\$\{batchId\}`/)
  assert.match(review,/onClose\(\)/)
})

test('review status comes from backend fields and imported diner count remains read-only',()=>{
  const draft={...line('2026-10-05','早餐',1,'主菜',1,'錯字',true),id:'line-1',resolution_status:'AMBIGUOUS',resolved_at:null,resolved_by:null,duplicate_conflict:false,excluded_at:null,excluded_by:null}
  assert.equal(menuImportStatus(draft),'AMBIGUOUS')
  assert.match(grid,/\{line\.diner_count\} 人/)
  assert.doesNotMatch(grid,/type="number"/)
  assert.match(review,/detail\.summary\.review_required_count/)
})

test('every persisted import line is editable while colors only communicate review state',()=>{
  assert.match(grid,/onClick=\{\(\)=>onLine\?\.\(line\)\}/)
  assert.match(grid,/disabled=\{!onLine\}/)
  assert.doesNotMatch(grid,/line\.review_required&&onLine/)
  assert.match(grid,/return'normal'/)
  assert.match(css,/\.menu-import-cell\.normal:not\(:disabled\):hover/)
  assert.match(grid,/menu-import-edit-hint/)
  assert.match(review,/Excel 原始菜名/)
  assert.match(review,/目前菜色/)
  assert.match(review,/確認變更/)
})

test('excluded lines use persisted exclude and restore actions followed by authoritative GET',()=>{
  assert.match(review,/\/lines\/\$\{line\.id\}\/exclude/)
  assert.match(review,/\/lines\/\$\{line\.id\}\/restore/)
  assert.match(review,/只會從本次 Excel 匯入排除/)
  assert.match(review,/恢復此菜色/)
  assert.match(grid,/return'excluded'/)
  assert.match(grid,/menu-import-excluded-badge/)
  assert.match(css,/\.menu-import-cell\.excluded/)
  assert.match(css,/text-decoration:line-through/)
  assert.doesNotMatch(review,/setDetail\([^)]*resolution_status/)
})

test('duplicate conflicts have priority over review state and are summarized separately',()=>{
  const excludedIndex=grid.indexOf("return'excluded'")
  const duplicateIndex=grid.indexOf("return'duplicate'")
  const reviewIndex=grid.indexOf("return'needs-review'")
  assert.ok(excludedIndex>-1&&excludedIndex<duplicateIndex&&duplicateIndex<reviewIndex)
  assert.match(grid,/重複菜色/)
  assert.match(grid,/同一天同餐別已有相同菜色/)
  assert.match(css,/\.menu-import-cell\.duplicate\{background:#fff4e5/)
  assert.match(review,/detail\.summary\.duplicate_conflict_count/)
  assert.match(review,/detail\.summary\.excluded_count/)
  assert.match(review,/有效菜色/)
})

test('wide import matrix scrolls horizontally and responsive dialogs keep existing menu editor flow',()=>{
  assert.match(css,/\.menu-import-grid-wrap\{overflow:auto/)
  assert.match(css,/\.menu-import-grid\{width:100%;min-width:980px/)
  assert.match(css,/@media\(max-width:800px\)/)
  assert.match(menus,/onOpen\(item\)/)
})
