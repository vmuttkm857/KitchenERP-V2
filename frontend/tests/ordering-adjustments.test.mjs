import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {adjustmentDateRange,adjustmentStatusLabels,formatAdjustmentQuantity,groupAdjustmentLines,staleReasonLabel} from '../src/features/order_adjustments/view.ts'

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

test('hierarchy preserves API order and groups Menu date meal dish ingredient',()=>{
  const base={snapshot_item_id:'s',source_line_key:'k',source_menu_id:'menu-b',menu_name_snapshot:'菜單 B',source_menu_day_id:'day',requirement_date:'2026-09-02',source_meal_type_id:'meal',meal_type_name_snapshot:'午餐',meal_type_sort_order_snapshot:1,source_menu_meal_type_column_id:null,menu_meal_type_column_sort_order_snapshot:null,source_menu_dish_id:'dish-a',menu_dish_sort_order_snapshot:1,source_dish_id:'dish',dish_code_snapshot:'01',dish_name_snapshot:'菜 A',diner_count_snapshot:30,source_dish_ingredient_id:'di',dish_ingredient_sort_order_snapshot:1,source_ingredient_id:'ingredient',ingredient_code_snapshot:'I',ingredient_name_snapshot:'食材',source_supplier_id:null,supplier_name_snapshot:null,quantity_per_person_snapshot:'1.0',loss_rate_snapshot:'0',recipe_unit_snapshot:'g',system_quantity:'30.0000',system_unit:'g',adjusted_quantity:null,effective_quantity:'30.0000',modified:false,stale:false,stale_reasons:[]}
  const lines=[{...base,id:'2'},{...base,id:'1',source_menu_id:'menu-a',menu_name_snapshot:'菜單 A'}]
  const grouped=groupAdjustmentLines(lines)
  assert.deepEqual(grouped.map(item=>item.id),['menu-b','menu-a'])
  assert.equal(grouped[0].dates[0].meals[0].dishes[0].lines[0].id,'2')
  assert.match(page,/ordering-adjustment-menu/)
  assert.match(page,/ordering-adjustment-day/)
  assert.match(page,/ordering-adjustment-meal/)
  assert.match(page,/ordering-adjustment-dish/)
})

test('status date range stale reasons and responsive presentation are available',()=>{
  assert.deepEqual(adjustmentStatusLabels,{draft:'草稿',confirmed:'已確認',cancelled:'已取消'})
  assert.equal(adjustmentDateRange({menu_ids:['m'],start_date:'2026-09-01',end_date:'2026-09-07'}),'2026-09-01～2026-09-07')
  assert.equal(staleReasonLabel('NEW_SOURCE_LINE'),'目前來源新增了食材項目')
  assert.match(page,/來源資料已變更，此調整單需要重新建立/)
  assert.match(css,/\.ordering-adjustment-status\.is-draft/)
  assert.match(css,/\.ordering-adjustment-hierarchy/)
  assert.match(css,/@media\(max-width:760px\)/)
})
