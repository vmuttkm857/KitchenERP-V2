import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {adjustmentDateRange,adjustmentStatusLabels,formatAdjustmentQuantity,staleReasonLabel} from '../src/features/order_adjustments/view.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/app/App.tsx')
const page=read('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx')
const api=read('../src/features/order_adjustments/api.ts')
const types=read('../src/features/order_adjustments/types.ts')
const client=read('../src/api/client.ts')
const css=read('../src/styles/global.css')

test('ordering adjustment navigation is added without removing existing purchasing pages',()=>{
  assert.match(app,/\['order-adjustments','叫貨調整'\]/)
  assert.match(app,/page==='order-adjustments'&&<OrderingAdjustmentsPage initialSheetId=\{requirementAdjustment\?\.id\} onReview=\{openAdjustmentRequirements\}\/>/)
  for(const label of ['食材需求','固定需求快照','正式採購'])assert.match(app,new RegExp(label))
})

test('Phase 2A API wrappers use list create and detail endpoints',()=>{
  assert.match(api,/\/order-adjustments\?\$\{query\}/)
  assert.match(api,/apiRequest<OrderingAdjustmentDetail>\('\/order-adjustments',\{method:'POST'/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}`/)
  for(const parameter of ['status','start_date','end_date','menu_id'])assert.match(api,new RegExp(`query\\.set\\('${parameter}'`))
})

test('saved adjustment navigates into the existing requirements workflow',()=>{
  assert.match(page,/前往食材需求/)
  assert.match(page,/onReview\?\.\(detail\)/)
  assert.match(app,/setRequirementAdjustment\(detail\)/)
  assert.match(app,/adjustmentContext=\{requirementAdjustment\}/)
})

test('list create duplicate and read-only detail states are represented',()=>{
  assert.match(page,/目前沒有叫貨調整單/)
  assert.match(page,/建立叫貨調整單/)
  assert.match(page,/已選 \{selected\.size\} 份菜單/)
  assert.match(page,/menu_ids:\[\.\.\.selected\.keys\(\)\]/)
  assert.match(page,/ADJUSTMENT_DRAFT_EXISTS/)
  assert.match(page,/繼續編輯原草稿/)
  assert.match(page,/查看已確認調整單/)
  assert.match(page,/此叫貨調整已完成確認，數量已鎖定/)
  assert.match(page,/此調整單已取消，目前僅供查看/)
})

test('create dialog suggests menu date ranges without removing manual date editing',()=>{
  assert.match(page,/suggestedStart/)
  assert.match(page,/suggestedEnd/)
  assert.match(page,/if\(!datesTouched\)applySuggestedDates/)
  assert.match(page,/所選菜單日期不完全相同/)
  assert.match(page,/套用建議範圍/)
  assert.match(page,/setDatesTouched\(true\)/)
  assert.match(page,/可依實際作業需要縮短為部分日期/)
})

test('confirmed list rows expose the requirements shortcut while preserving all actions',()=>{
  assert.match(page,/item\.status==='confirmed'&&<button onClick=\{\(\)=>onReview\(item\.id\)\}>前往食材需求/)
  assert.match(page,/await getOrderingAdjustment\(sheetId\)/)
  assert.match(page,/item\.status==='draft'&&<button className="secondary-danger"/)
  assert.match(page,/ordering-adjustment-list-menu/)
  assert.match(page,/ordering-adjustment-list-range/)
})

test('draft lifecycle exposes explicit confirm and versioned delete actions',()=>{
  assert.match(page,/完成叫貨調整/)
  assert.match(page,/目前有尚未儲存的修改，請先儲存後再完成叫貨調整/)
  assert.match(page,/完成叫貨調整？/)
  assert.match(page,/已確認不代表已建立正式採購單/)
  assert.match(page,/confirmOrderingAdjustment\(detail\.id,detail\.lock_version\)/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/confirm`/)
  assert.match(api,/JSON\.stringify\(\{lock_version:lockVersion\}\)/)

  assert.match(page,/刪除叫貨調整單？/)
  assert.match(page,/尚未確認的調整數量將無法復原/)
  assert.match(page,/item\.status==='draft'&&<button className="secondary-danger"/)
  assert.match(page,/deleteOrderingAdjustment\(deleteTarget\.id,deleteTarget\.lock_version\)/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\?lock_version=\$\{lockVersion\}`/)
  assert.match(api,/method:'DELETE'/)
})

test('confirmed adjustment can be explicitly reopened without changing draft editing rules',()=>{
  assert.match(page,/detail\.status==='confirmed'&&<button className="secondary" disabled=\{reopening\}/)
  assert.match(page,/解除叫貨調整鎖定？/)
  assert.match(page,/原有人工叫貨數量與單位會完整保留/)
  assert.match(page,/reopenOrderingAdjustment\(detail\.id,detail\.lock_version\)/)
  assert.match(page,/已解除鎖定，可繼續修改叫貨量/)
  assert.match(page,/detail\.status!=='draft'\|\|detail\.stale/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/reopen`/)
  assert.match(page,/ADJUSTMENT_SYNC_REQUIRED/)
  assert.match(page,/原始菜單或食譜已變更，目前需要先完成菜單同步功能才能解除鎖定/)
})

test('draft adjustments expose explicit menu and recipe sync preview and apply APIs',()=>{
  assert.match(page,/detail\.status==='draft'&&<div className=\{`ordering-action-group ordering-sync-action/)
  assert.match(page,/同步最新菜單與食譜/)
  assert.match(page,/previewOrderingAdjustmentSync\(current\.id,current\.lock_version\)/)
  assert.match(page,/applyOrderingAdjustmentSync\(detail\.id,\{lock_version:syncPreview\.lock_version,expected_source_fingerprint:syncPreview\.preview_source_fingerprint/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/sync-preview`/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/sync`/)
  assert.match(types,/accepted_removed_source_line_keys:string\[\]/)
  assert.match(types,/reset_adjustment_line_ids:string\[\]/)
})

test('sync preview protects removed quantities and does not transfer old dish adjustments',()=>{
  assert.match(page,/舊菜的人工量不會轉移到新菜/)
  assert.match(page,/這是來源配置變更提示，不代表舊菜色的人工數量會轉移至新菜色/)
  assert.match(page,/原人工叫貨：\{syncQuantity\(change\.previous,'effective'\)\}/)
  assert.match(page,/同步後該來源明細將移除/)
  assert.match(page,/人工量尚未設定/)
  assert.match(page,/requiredRemoved\.every\(key=>acceptedRemoved\.has\(key\)\)/)
  assert.match(page,/disabled=\{!applyReady\}/)
  assert.match(page,/accepted_removed_source_line_keys:acceptedRemoved/)
})

test('sync unit conflicts require an explicit reset decision',()=>{
  assert.match(page,/單位衝突（逐筆處理）/)
  assert.match(page,/無法安全換算成新來源單位/)
  assert.match(page,/重設此筆人工數量/)
  assert.match(page,/requiredResets\.every\(id=>resetLines\.has\(id\)\)/)
  assert.match(page,/reset_adjustment_line_ids:resetLineIds/)
  assert.match(page,/checked=\{Boolean\(id\)&&resetLines\.has\(id\)\}/)
})

test('sync protects unsaved edits and stale drafts from unsafe saves',()=>{
  assert.match(page,/if\(dirtyIds\.length\)\{setSyncDirtyOpen\(true\);return\}/)
  assert.match(page,/儲存後預覽/)
  assert.match(page,/捨棄修改並預覽/)
  assert.match(page,/來源已變更，舊來源上的未儲存輸入不能安全儲存/)
  assert.match(page,/\{!stale&&<button disabled=\{busy\|\|invalid\}/)
  assert.match(page,/clearEditorDirty\(\);onDetailChange\(updated\);setSyncDirtyOpen\(false\);await loadSyncPreview\(updated\)/)
})

test('sync errors preserve editor data and identify recovery actions',()=>{
  for(const code of ['SYNC_SOURCE_CHANGED','SYNC_REMOVALS_NOT_ACCEPTED','SYNC_UNIT_CONFLICT','ADJUSTMENT_DRAFT_EXISTS','LOCK_VERSION_CONFLICT','SNAPSHOT_LOCKED','INVALID_ADJUSTMENT_STATUS'])assert.match(page,new RegExp(code))
  assert.match(page,/同步套用失敗，原有人工叫貨量仍完整保留/)
  assert.match(page,/if\(code==='SYNC_SOURCE_CHANGED'\|\|code==='LOCK_VERSION_CONFLICT'\)setSyncPreview\(null\)/)
  assert.match(page,/if\(syncPreviewingRef\.current\|\|current\.status!=='draft'\)return/)
  assert.match(page,/if\(!syncPreview\|\|syncApplyingRef\.current\)return/)
  assert.match(page,/syncApplyingRef\.current=true/)
})

test('lifecycle status, errors and actions stay explicit',()=>{
  for(const label of ['草稿','已確認','已失效','已取消'])assert.match(page,new RegExp(label))
  for(const code of ['LOCK_VERSION_CONFLICT','ADJUSTMENT_STALE','CONFIRMED_DELETE_FORBIDDEN','CANCELLED_DELETE_FORBIDDEN','SNAPSHOT_LOCKED'])assert.match(page,new RegExp(code))
  assert.match(page,/detail\.status==='draft'&&!detail\.stale/)
  assert.match(page,/detail\.status==='confirmed'/)
  assert.match(page,/前往食材需求/)
  assert.match(css,/\.ordering-adjustment-status\.is-stale/)
  assert.match(css,/\.ordering-adjustment-list-actions/)
  assert.match(css,/\.ordering-delete-summary/)
})

test('structured API detail is preserved for duplicate draft handling',()=>{
  assert.match(client,/let detail: unknown = null/)
  assert.match(client,/new ApiError\(response\.status, message, detail\)/)
  assert.match(client,/public readonly detail: unknown = null/)
})

test('quantities stay string typed and presentation only trims trailing zeroes',()=>{
  for(const field of ['system_quantity','adjusted_quantity','effective_quantity'])assert.match(types,new RegExp(`${field}:string`))
  for(const field of ['adjusted_unit','effective_unit'])assert.match(types,new RegExp(`${field}:string`))
  assert.equal(formatAdjustmentQuantity('1.7100'),'1.71')
  assert.equal(formatAdjustmentQuantity('2.0000'),'2')
  assert.equal(formatAdjustmentQuantity('not-a-number'),'not-a-number')
})

test('draft exposes three confirmed server-side batch unit conversions',()=>{
  for(const label of ['g、斤 → kg','g → kg','斤 → g'])assert.match(page,new RegExp(label))
  assert.match(page,/批次換算叫貨單位？/)
  assert.match(page,/數量會同步精確換算，其他單位不受影響/)
  assert.match(page,/convertOrderingAdjustmentUnits\(detail\.id,detail\.lock_version,unitConversion\)/)
  assert.match(page,/onDetailChange\(updated\)/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/convert-units`/)
  assert.match(api,/method:'POST'/)
  assert.match(page,/請先儲存或還原目前修改，再進行批次單位換算/)
})

test('detail downloads saved adjusted weekly Excel with explicit multi-menu selection',()=>{
  assert.match(page,/下載 Excel/)
  assert.match(page,/下載調整後廚房配料表/)
  assert.match(page,/這張調整單包含多份菜單，請選擇要匯出的菜單/)
  assert.match(page,/detail\.source_menus\.length===1/)
  assert.match(page,/downloadOrderingAdjustmentWeekly\(detail\.id,menuId\)/)
  assert.match(page,/目前有尚未儲存的修改，請先儲存後再下載 Excel/)
  assert.match(api,/apiDownload\(`\/exports\/order-adjustments\/\$\{sheetId\}\/weekly-ingredients\.xlsx/)
  assert.match(api,/menu_id:menuId/)
})

test('detail uses weekly matrix with menu tabs and compact ingredient rows',()=>{
  assert.match(page,/buildAdjustmentMenuMatrix/)
  assert.match(page,/ordering-adjustment-tabs/)
  assert.match(page,/ordering-adjustment-matrix/)
  assert.match(page,/matrix-meal-cell/)
  assert.match(page,/matrix-column-cell/)
  assert.match(page,/ordering-adjustment-cell-dish/)
  assert.match(page,/ordering-adjustment-cell-line/)
  assert.doesNotMatch(page,/ingredient_code_snapshot/)
})

test('status date range stale reasons and responsive presentation are available',()=>{
  assert.deepEqual(adjustmentStatusLabels,{draft:'草稿',confirmed:'已確認',cancelled:'已取消'})
  assert.equal(adjustmentDateRange({menu_ids:['m'],start_date:'2026-09-01',end_date:'2026-09-07'}),'2026-09-01～2026-09-07')
  assert.equal(staleReasonLabel('NEW_SOURCE_LINE'),'目前來源新增了食材項目')
  assert.match(page,/來源資料已變更，請同步最新菜單與食譜後再繼續編輯/)
  assert.match(css,/\.ordering-adjustment-status\.is-draft/)
  assert.match(css,/\.ordering-adjustment-matrix/)
  assert.match(css,/position:sticky/)
  assert.match(css,/@media\(max-width:760px\)/)
})

test('previous quantity reuse is explicit preview then authoritative apply',()=>{
  assert.match(page,/沿用上一張叫貨量/)
  assert.match(page,/請先儲存或還原目前修改/)
  assert.match(page,/listOrderingAdjustments\(\{page:1,pageSize:100\}\)/)
  assert.match(page,/選擇上一份菜單/)
  assert.match(page,/previewOrderingAdjustmentReuse/)
  assert.match(page,/applyOrderingAdjustmentReuse/)
  assert.match(page,/line\.status==='safe_to_reuse'/)
  assert.match(page,/selected_current_line_ids:\[\.\.\.selected\]/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/reuse-preview`/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}\/reuse`/)
})

test('reuse preview explains partial menu editing without overwriting changed lines',()=>{
  for(const text of ['可直接沿用','比對後需人工判斷','新菜／已更換','無法唯一比對','本次已有人工調整，不會覆蓋'])assert.match(page,new RegExp(text))
  assert.match(page,/沒有變更的菜色可直接沿用/)
  assert.match(page,/disabled=\{line\.status!=='safe_to_reuse'\}/)
  assert.match(types,/safe_to_reuse.*reference_only.*no_match.*ambiguous/)
  assert.match(css,/\.ordering-reuse-summary/)
  assert.match(css,/\.ordering-reuse-line\.is-reference_only/)
})

test('actionable reference-only rows use explicit red review presentation',()=>{
  assert.match(page,/reviewLineIds/)
  assert.match(types,/review_required:boolean/)
  assert.match(page,/detail\.lines\.filter\(line=>line\.review_required\)/)
  assert.match(page,/\{reviewLineIds\.size\} 項叫貨量需要確認/)
  assert.match(page,/ordering-review-banner/)
  assert.match(page,/ordering-adjustment-cell-dish\$\{dishNeedsReview\?' needs-review'/)
  assert.match(page,/ordering-adjustment-cell-line\$\{dirty\?' is-dirty':''\}\$\{needsReview\?' needs-review'/)
  assert.match(page,/ordering-review-badge">需確認/)
  assert.doesNotMatch(page,/setReviewLineIds/)
  assert.match(page,/onDetailChange\(updated\);setMessage\('草稿已儲存'\)/)
  assert.match(css,/\.ordering-review-banner[^}]*background:#fff1f2[^}]*border-left:4px solid #a72b38/)
  assert.match(css,/\.ordering-adjustment-cell-dish\.needs-review[^}]*background:#fff5f6[^}]*border-left:4px solid #a72b38/)
  assert.match(css,/\.ordering-adjustment-cell-line\.needs-review/)
  assert.match(css,/\.ordering-review-badge/)
  assert.doesNotMatch(css,/\.ordering-reuse-line\.is-reference_only\{[^}]*#fff8e7/)
})

test('reuse completion is persisted and repeat comparison requires confirmation',()=>{
  for(const field of ['last_reuse_source_sheet_id','reuse_applied_at','reuse_applied_by'])assert.match(types,new RegExp(`${field}:string\\|null`))
  assert.match(page,/detail\.reuse_applied_at&&<span className="ordering-reuse-status">✓ 已沿用上一張叫貨量<\/span>/)
  assert.match(page,/detail\.reuse_applied_at\?'重新比對':'沿用上一張叫貨量'/)
  assert.match(page,/重新比對上一張叫貨量？/)
  assert.match(page,/繼續重新比對/)
  assert.match(page,/setReuseAgainOpen\(false\);setReuseOpen\(true\)/)
  assert.match(page,/onCancel=\{\(\)=>setReuseAgainOpen\(false\)\}/)
  assert.match(page,/比對後需人工判斷/)
  assert.match(page,/目前草稿尚待確認的數量仍以上方紅色提示為準/)
  assert.match(css,/\.ordering-reuse-status/)
  assert.match(css,/\.ordering-reuse-comparison-note/)
})
