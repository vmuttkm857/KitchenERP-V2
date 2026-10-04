import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {buildAdjustmentUpdates,decimalStringsEqual,dirtyAdjustmentLineIds,initialAdjustmentValues,normalizeDecimalString,validateAdjustmentQuantity} from '../src/features/order_adjustments/editor.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const page=read('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx')
const api=read('../src/features/order_adjustments/api.ts')
const css=read('../src/styles/global.css')
const line=(id,dish,system,adjusted=null)=>({id,source_menu_dish_id:dish,system_quantity:system,adjusted_quantity:adjusted})

test('initial values prefer persisted adjustment and otherwise use system quantity without PATCH',()=>{
  const lines=[line('a','dish-a','1.710000','2.000000'),line('b','dish-b','2.350000')]
  assert.deepEqual(initialAdjustmentValues(lines),{a:'2',b:'2.35'})
  assert.doesNotMatch(initialAdjustmentValues.toString(),/updateOrderingAdjustmentLines|apiRequest/)
})

test('same ingredient source lines remain independent by line id and dish',()=>{
  const lines=[line('a','dish-a','1.710000'),line('b','dish-b','2.350000')]
  const values={...initialAdjustmentValues(lines),a:'2'}
  assert.deepEqual(dirtyAdjustmentLineIds(lines,values),['a'])
  assert.equal(values.b,'2.35')
})

test('decimal equality is string safe and never relies on floating point',()=>{
  assert.equal(decimalStringsEqual('1','1.0'),true)
  assert.equal(decimalStringsEqual('1.000000','1'),true)
  assert.equal(decimalStringsEqual('0','0.000000'),true)
  assert.equal(decimalStringsEqual('1.000001','1.000000'),false)
  assert.equal(normalizeDecimalString('0001.500000'),'1.5')
  assert.doesNotMatch(read('../src/features/order_adjustments/editor.ts'),/parseFloat|Number\(|toFixed/)
})

test('dirty count clears when a value returns to the persisted decimal value',()=>{
  const lines=[line('a','dish-a','1','2.000000'),line('b','dish-b','3')]
  assert.deepEqual(dirtyAdjustmentLineIds(lines,{a:'2.5',b:'4'}),['a','b'])
  assert.deepEqual(dirtyAdjustmentLineIds(lines,{a:'2',b:'3.000000'}),[])
})

test('quantity validation accepts zero and six decimals but rejects unsafe input',()=>{
  for(const valid of ['0','1','1.5','1.500000','0.000001'])assert.equal(validateAdjustmentQuantity(valid),null)
  assert.equal(validateAdjustmentQuantity('-1'),'不可小於 0')
  assert.equal(validateAdjustmentQuantity(''),'請輸入實際叫貨量')
  assert.equal(validateAdjustmentQuantity('abc'),'請輸入有效的小數')
  assert.equal(validateAdjustmentQuantity('1.2.3'),'請輸入有效的小數')
  assert.equal(validateAdjustmentQuantity('1.0000001'),'最多 6 位小數')
})

test('batch payload sends only dirty lines and reset-to-system becomes null',()=>{
  const lines=[line('a','dish-a','1.710000','2'),line('b','dish-b','2.35'),line('c','dish-c','4.28','5')]
  assert.deepEqual(buildAdjustmentUpdates(lines,{a:'1.710000',b:'3',c:'5.000000'}),[
    {id:'a',adjusted_quantity:null},{id:'b',adjusted_quantity:'3'},
  ])
  assert.match(api,/method:'PATCH'/)
  assert.match(page,/lock_version:detail\.lock_version/)
})

test('editor exposes dirty persisted and accessible input states without automatic save',()=>{
  assert.match(page,/inputMode="decimal"/)
  assert.match(page,/aria-label=\{`\$\{dish\.name\} - \$\{line\.ingredient_name_snapshot\} 實際叫貨量`\}/)
  assert.match(page,/人工調整/)
  assert.match(page,/已修改/)
  assert.match(page,/>恢復<\/button>/)
  assert.match(page,/尚有 \$\{dirtyIds\.length\} 筆修改未儲存/)
  assert.match(page,/if\(event\.key==='Enter'\)event\.preventDefault\(\)/)
  assert.match(css,/\.ordering-adjustment-cell-line\.is-dirty/)
})

test('successful save uses authoritative response and error paths retain local values',()=>{
  assert.match(page,/onDetailChange\(updated\);setMessage\('草稿已儲存'\)/)
  assert.match(page,/LOCK_VERSION_CONFLICT/)
  assert.match(page,/這張叫貨調整單已在其他地方被修改，請重新載入最新資料/)
  assert.match(page,/ADJUSTMENT_STALE/)
  assert.match(page,/修改尚未遺失/)
  assert.doesNotMatch(page,/catch\([^)]*\)\s*\{[^}]*setValues\(/s)
})

test('reload and back require confirmation only when unsaved lines exist',()=>{
  assert.match(page,/if\(dirtyIds\.length\)setConfirmation\('reload'\)/)
  assert.match(page,/if\(dirtyIds\.length\)setConfirmation\('back'\)/)
  assert.match(page,/重新載入會捨棄尚未儲存的修改/)
  assert.match(page,/尚有未儲存的叫貨量修改，確定要離開嗎/)
  assert.match(page,/useEditorDirty\(dirtyIds\.length>0\)/)
})

test('confirmed cancelled and stale sheets remain read-only while drafts save in one action',()=>{
  assert.match(page,/const readOnly=detail\.status!=='draft'\|\|detail\.stale/)
  assert.match(page,/readOnly\?<b>\{formatAdjustmentQuantity\(line\.effective_quantity\)\}/)
  assert.match(page,/儲存草稿/)
  assert.match(page,/updateOrderingAdjustmentLines\(detail\.id,/)
})
