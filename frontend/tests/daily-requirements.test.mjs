import assert from 'node:assert/strict'
import test from 'node:test'

import { dailyRowsTsv,filterSupplierRows,groupDailyByDate,groupDailyBySupplier,sortDailyRows,supplierOptions,supplierRowsTsv } from '../src/features/requirements/dailyRequirements.ts'
import { addDecimals,formatMoney,formatQuantity,plainDecimal } from '../src/utils/numbers.ts'
import { snapshotDailyRows,snapshotPurchaseAction } from '../src/features/snapshots/snapshotRequirements.ts'

const row=(changes={})=>({requirement_date:'2026-10-05',menu_id:'menu-1',menu_name:'菜單甲',supplier_id:'supplier-1',supplier_code:'S1',supplier_name:'供應商甲',ingredient_id:'ingredient-1',ingredient_code:'I1',ingredient_name:'高麗菜',quantity:'30.000000',unit:'kg',...changes})

test('date view keeps same-day menus separate',()=>{
  const groups=groupDailyByDate([row(),row({menu_id:'menu-2',menu_name:'菜單乙'})])
  assert.equal(groups.length,1)
  assert.deepEqual(groups[0].groups[0].menus.map(menu=>menu.menu_id).sort(),['menu-1','menu-2'])
})

test('supplier view nests dates then menus',()=>{
  const groups=groupDailyBySupplier([row(),row({requirement_date:'2026-10-06'}),row({supplier_id:null,supplier_name:null})])
  assert.equal(groups.length,2)
  const supplier=groups.find(group=>group.key==='supplier-1')
  assert.deepEqual(supplier.groups.map(group=>group.key),['2026-10-05','2026-10-06'])
  assert.equal(groups.find(group=>group.key==='unassigned').label,'未指定供應商')
})

test('flat daily and supplier ordering preserve same-name menu ids',()=>{
  const rows=[row({requirement_date:'2026-10-06'}),row({menu_id:'menu-2'}),row({supplier_id:null,supplier_name:null}),row()]
  const daily=sortDailyRows(rows,'daily');const supplier=sortDailyRows(rows,'supplier')
  assert.equal(daily[0].requirement_date,'2026-10-05')
  assert.deepEqual([...new Set(daily.filter(item=>item.menu_name==='菜單甲').map(item=>item.menu_id))].sort(),['menu-1','menu-2'])
  assert.equal(supplier[0].supplier_name,null)
})

test('daily ordering finishes every Menu A supplier before Menu B',()=>{
  const rows=[row({menu_id:'menu-b',menu_name:'Menu B',supplier_id:'supplier-1'}),row({menu_id:'menu-a',menu_name:'Menu A',supplier_id:'supplier-2'}),row({menu_id:'menu-a',menu_name:'Menu A',supplier_id:'supplier-1'}),row({requirement_date:'2026-10-04',menu_id:'menu-b',menu_name:'Menu B'})]
  assert.deepEqual(sortDailyRows(rows,'daily').map(item=>`${item.requirement_date}:${item.menu_id}:${item.supplier_id}`),['2026-10-04:menu-b:supplier-1','2026-10-05:menu-a:supplier-1','2026-10-05:menu-a:supplier-2','2026-10-05:menu-b:supplier-1'])
})

test('supplier options are unique, include missing supplier, and filtering is exact',()=>{
  const rows=[row(),row({ingredient_id:'ingredient-2'}),row({supplier_id:null,supplier_name:null}),row({supplier_id:'supplier-2',supplier_name:'供應商乙'})]
  const options=supplierOptions(rows)
  assert.deepEqual(new Set(options.map(option=>option.key)),new Set(['supplier-1','supplier-2','unassigned']))
  assert.equal(options.find(option=>option.key==='unassigned').label,'未指定供應商')
  assert.equal(filterSupplierRows(rows,'supplier-1').length,2)
})

test('single supplier TSV contains only selected supplier and separates quantity from unit',()=>{
  const tsv=supplierRowsTsv([row({quantity:'22654.000000',unit:'KG'}),row({supplier_id:'supplier-2',supplier_name:'供應商乙'})],'supplier-1')
  assert.deepEqual(tsv.split('\n')[0].split('\t'),['使用日期','菜單','食材編號','食材','需求量','單位'])
  assert.deepEqual(tsv.split('\n')[1].split('\t'),['2026-10-05','菜單甲','I1','高麗菜','22654','KG'])
  assert.equal(tsv.includes('供應商乙'),false)
})

test('TSV has headers, separate quantity and unit cells, and numeric quantity has no comma',()=>{
  const tsv=dailyRowsTsv([row({quantity:'22654.000000',unit:'KG'})],'daily')
  assert.deepEqual(tsv.split('\n')[0].split('\t'),['使用日期','菜單','供應商','食材編號','食材','需求量','單位'])
  assert.deepEqual(tsv.split('\n')[1].split('\t'),['2026-10-05','菜單甲','供應商甲','I1','高麗菜','22654','KG'])
})

test('snapshot and purchase number formatting is display-only and decimal addition is exact',()=>{
  assert.equal(formatQuantity('178493.720000'),'178,493.72')
  assert.equal(formatQuantity('0.000000'),'0')
  assert.equal(formatMoney('130.600000'),'130.6')
  assert.equal(plainDecimal('178493.720000'),'178493.72')
  assert.equal(addDecimals(['0.1','0.2','30.000000']),'30.3')
})

test('snapshot rows use the shared daily ordering and supplier filter',()=>{
  const items=[{id:'item-1',ingredient_id:'ingredient-1',ingredient_code_snapshot:'I1',ingredient_name_snapshot:'高麗菜',supplier_id:'supplier-1',supplier_code_snapshot:'S1',supplier_name_snapshot:'供應商甲',source_summary:[{requirement_date:'2026-10-05',menu_id:'menu-b',menu_name:'Menu B',quantity:'1.2',unit:'kg'},{requirement_date:'2026-10-05',menu_id:'menu-a',menu_name:'Menu A',quantity:'0.8',unit:'kg'}]},{id:'item-2',ingredient_id:'ingredient-2',ingredient_code_snapshot:'I2',ingredient_name_snapshot:'鹽',supplier_id:null,supplier_code_snapshot:null,supplier_name_snapshot:null,source_summary:[{requirement_date:'2026-10-05',menu_id:'menu-a',menu_name:'Menu A',quantity:'2',unit:'kg'}]}]
  const rows=snapshotDailyRows(items);assert.deepEqual(sortDailyRows(rows,'daily').map(item=>item.menu_id),['menu-a','menu-a','menu-b'])
  assert.equal(filterSupplierRows(rows,'unassigned')[0].ingredient_code,'I2')
})

test('snapshot purchase action exposes create and open labels',()=>{
  assert.equal(snapshotPurchaseAction(null),'建立正式採購')
  assert.equal(snapshotPurchaseAction('purchase-1'),'前往正式採購')
})
