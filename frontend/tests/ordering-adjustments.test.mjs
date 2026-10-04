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
  assert.match(app,/page==='order-adjustments'&&<OrderingAdjustmentsPage\/>/)
  for(const label of ['食材需求','固定需求快照','正式採購'])assert.match(app,new RegExp(label))
})

test('Phase 2A API wrappers use list create and detail endpoints',()=>{
  assert.match(api,/\/order-adjustments\?\$\{query\}/)
  assert.match(api,/apiRequest<OrderingAdjustmentDetail>\('\/order-adjustments',\{method:'POST'/)
  assert.match(api,/`\/order-adjustments\/\$\{sheetId\}`/)
  for(const parameter of ['status','start_date','end_date','menu_id'])assert.match(api,new RegExp(`query\\.set\\('${parameter}'`))
})

test('list create duplicate and read-only detail states are represented',()=>{
  assert.match(page,/目前沒有叫貨調整單/)
  assert.match(page,/建立叫貨調整單/)
  assert.match(page,/已選 \{selected\.size\} 份菜單/)
  assert.match(page,/menu_ids:\[\.\.\.selected\.keys\(\)\]/)
  assert.match(page,/ADJUSTMENT_DRAFT_EXISTS/)
  assert.match(page,/繼續編輯原草稿/)
  assert.match(page,/查看已確認調整單/)
  assert.match(page,/此調整單為\{adjustmentStatusLabels\[detail\.status\]\}狀態，目前僅供查看/)
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
