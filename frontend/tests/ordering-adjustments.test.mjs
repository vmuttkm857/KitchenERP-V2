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
  assert.equal(formatAdjustmentQuantity('1.7100'),'1.71')
  assert.equal(formatAdjustmentQuantity('2.0000'),'2')
  assert.equal(formatAdjustmentQuantity('not-a-number'),'not-a-number')
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
  assert.match(page,/來源資料已變更，此調整單需要重新建立/)
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
  assert.match(page,/detail\.reuse_applied_at\?<><span className="ordering-reuse-status">✓ 已沿用上一張叫貨量<\/span>/)
  assert.match(page,/>重新比對<\/button>/)
  assert.match(page,/重新比對上一張叫貨量？/)
  assert.match(page,/繼續重新比對/)
  assert.match(page,/setReuseAgainOpen\(false\);setReuseOpen\(true\)/)
  assert.match(page,/onCancel=\{\(\)=>setReuseAgainOpen\(false\)\}/)
  assert.match(page,/比對後需人工判斷/)
  assert.match(page,/目前草稿尚待確認的數量仍以上方紅色提示為準/)
  assert.match(css,/\.ordering-reuse-status/)
  assert.match(css,/\.ordering-reuse-comparison-note/)
})
