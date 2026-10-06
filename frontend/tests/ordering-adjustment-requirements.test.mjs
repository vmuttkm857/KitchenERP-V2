import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/app/App.tsx')
const adjustment=read('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx')
const requirements=read('../src/features/requirements/RequirementsPage.tsx')
const api=read('../src/features/order_adjustments/api.ts')

test('standalone adjustment requirements review was removed',()=>{
  assert.doesNotMatch(api,/order-adjustments\/\$\{sheetId\}\/requirements/)
  assert.doesNotMatch(requirements,/AdjustmentRequirementsReview|實際叫貨需求|系統理論需求/)
  assert.match(requirements,/每日需求/)
  assert.match(requirements,/單一供應商/)
  assert.match(requirements,/總需求/)
})

test('adjustment navigation preserves full explicit calculation context',()=>{
  assert.match(adjustment,/前往食材需求/)
  assert.match(adjustment,/onReview\?\.\(detail\)/)
  assert.match(app,/setRequirementAdjustment\(detail\)/)
  assert.match(requirements,/setSelectedMenuMap\(initialMenus\(\)\)/)
  assert.match(requirements,/adjustmentContext\.criteria\.start_date/)
  assert.match(requirements,/basis==='actual'&&activeAdjustment/)
  assert.match(requirements,/ordering_adjustment_sheet_ids:\[activeAdjustment\.id\]/)
})

test('calculate export and snapshot share the same authoritative criteria',()=>{
  assert.match(requirements,/JSON\.stringify\(requestCriteria\)/)
  assert.match(requirements,/JSON\.stringify\(\{criteria:resultCriteria\}\)/)
  assert.match(requirements,/body:JSON\.stringify\(resultCriteria\)/)
  assert.match(requirements,/\/requirements\/calculate/)
  assert.match(requirements,/\/exports\/requirements\/xlsx/)
  assert.match(requirements,/\/requirement-snapshots/)
})

test('quantity basis is explicit before calculation and retains adjustment context',()=>{
  assert.match(requirements,/③ 數量依據/)
  assert.match(requirements,/④ 計算/)
  assert.match(requirements,/type="radio" name="quantity-basis" value="theoretical"/)
  assert.match(requirements,/type="radio" name="quantity-basis" value="actual"/)
  assert.match(requirements,/checked=\{quantityBasis==='theoretical'\}/)
  assert.match(requirements,/checked=\{quantityBasis==='actual'\}/)
  assert.match(requirements,/目前使用：\{basisLabel\}/)
  assert.match(requirements,/可用實際叫貨來源/)
  assert.match(requirements,/Rev\.\{activeAdjustment\.revision\}/)
  assert.doesNotMatch(requirements,/取消套用叫貨調整/)
  assert.match(requirements,/setQuantityBasis\(next\)/)
  assert.match(requirements,/setResult\(null\)/)
})

test('sidebar and adjustment navigation choose safe initial quantity basis',()=>{
  assert.match(requirements,/useState<QuantityBasis>\(adjustmentContext\?'actual':'theoretical'\)/)
  assert.match(requirements,/if\(!adjustmentContext\)\{setActiveAdjustment\(null\);setQuantityBasis\('theoretical'\)/)
  assert.match(requirements,/setActiveAdjustment\(adjustmentContext\);setQuantityBasis\('actual'\)/)
  assert.match(requirements,/disabled=\{loading\|\|!activeAdjustment\}/)
  assert.match(requirements,/尚未選擇叫貨調整單/)
  assert.match(requirements,/role="radiogroup"/)
})

test('mode switch clears stale results but preserves menus dates and adjustment',()=>{
  const switchBody=requirements.match(/function changeQuantityBasis[\s\S]*?\n  function showCopyMessage/)?.[0]??''
  assert.match(switchBody,/setQuantityBasis\(next\)/)
  assert.match(switchBody,/setCalculatedBasis\(null\)/)
  assert.match(switchBody,/setResult\(null\)/)
  assert.match(switchBody,/數量依據已切換，請重新計算需求量/)
  assert.doesNotMatch(switchBody,/setActiveAdjustment|setSelectedMenuMap|setStartDate|setEndDate/)
})

test('calculate export and snapshot use the currently selected quantity basis',()=>{
  assert.match(requirements,/const criteriaForBasis=\(basis:QuantityBasis\)=>\(\{menu_ids:menuIds,\.\.\.criteriaDates,\.\.\.\(basis==='actual'&&activeAdjustment/)
  assert.match(requirements,/const resultCriteria=criteriaForBasis\(calculatedBasis\?\?quantityBasis\)/)
  assert.match(requirements,/本次將依「\{basisLabel\}」計算/)
  assert.match(requirements,/目前數量依據：\{calculatedBasisLabel\}/)
  assert.match(requirements,/將以目前「\{basisLabel\}」建立固定需求快照/)
})

test('completed result has an independent quantity basis summary card',()=>{
  assert.match(requirements,/setCalculatedBasis\(quantityBasis\)/)
  assert.match(requirements,/result&&calculatedBasis/)
  assert.match(requirements,/目前數量依據：\{calculatedBasisLabel\}/)
  assert.match(requirements,/<small>數量依據<\/small><strong>\{calculatedBasisLabel\}<\/strong>/)
  assert.match(requirements,/已套用叫貨調整/)
  assert.match(requirements,/依配方與人數計算/)
})

test('structured adjustment failures have friendly Traditional Chinese messages',()=>{
  assert.match(requirements,/ADJUSTMENT_STALE/)
  assert.match(requirements,/來源菜單已變更，請回到叫貨調整重新建立／更新/)
  assert.match(requirements,/ADJUSTMENT_STATUS_INVALID/)
  assert.match(requirements,/已確認或取消，不能套用到即時食材需求/)
  assert.match(requirements,/ADJUSTMENT_DUPLICATE_OVERRIDE/)
})
