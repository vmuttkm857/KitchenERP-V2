import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

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
  assert.match(requirements,/<legend>數量依據<\/legend>/)
  assert.match(requirements,/B\. 計算操作/)
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
  const switchBody=requirements.match(/function changeQuantityBasis[\s\S]*?\n  function openPurchaseFlow/)?.[0]??''
  assert.match(switchBody,/setQuantityBasis\(next\)/)
  assert.match(switchBody,/invalidateResult/)
  assert.match(switchBody,/數量依據已切換，請重新計算需求量/)
  assert.doesNotMatch(switchBody,/setActiveAdjustment|setSelectedMenuMap|setStartDate|setEndDate/)
})

test('calculate export and snapshot use the currently selected quantity basis',()=>{
  assert.match(requirements,/const criteriaForBasis=\(basis:QuantityBasis\)=>\(\{menu_ids:menuIds,\.\.\.criteriaDates,\.\.\.\(basis==='actual'&&activeAdjustment/)
  assert.match(requirements,/\[resultCriteria,setResultCriteria\]=useState<CalculationCriteria\|null>\(null\)/)
  assert.match(requirements,/setResultCriteria\(requestCriteria\)/)
  assert.doesNotMatch(requirements,/const resultCriteria=criteriaForBasis\(calculatedBasis\?\?quantityBasis\)/)
  assert.match(requirements,/本次將依「\{basisLabel\}」計算/)
  assert.match(requirements,/目前數量依據：\{calculatedBasisLabel\}/)
  assert.match(requirements,/將以目前「\{calculatedBasisLabel\}」建立固定需求快照/)
})

test('prefilled workflow remains editable and condition changes invalidate old results',()=>{
  assert.match(requirements,/已從叫貨調整單帶入作業條件/)
  assert.match(requirements,/實際叫貨｜Rev\./)
  assert.match(requirements,/function invalidateResult/)
  assert.match(requirements,/setCalculatedBasis\(null\);setResult\(null\)/)
  assert.match(requirements,/function toggle\(menu:Menu\)[\s\S]*invalidateResult\(\)/)
  assert.match(requirements,/setStartDate\(e\.target\.value\);invalidateResult\(\)/)
  assert.match(requirements,/setEndDate\(e\.target\.value\);invalidateResult\(\)/)
})

test('snapshot is required before the explicit purchase navigation',()=>{
  assert.match(requirements,/儲存為固定需求快照/)
  assert.match(requirements,/前往正式採購/)
  assert.match(requirements,/請先將目前結果儲存為固定需求快照/)
  assert.match(requirements,/setSavedSnapshotId\(snapshot\.id\)/)
  assert.match(requirements,/existing_snapshot_id/)
  assert.match(requirements,/onOpenSnapshot\?\.\(savedSnapshotId\)/)
  assert.match(app,/setSnapshotId\(id\);setPage\('snapshots'\)/)
  assert.match(app,/SnapshotsPage initialId=\{snapshotId\}/)
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

test('H01 coverage failures explain why calculation stopped without falling back to live menus',()=>{
  // Evaluate the real pure error mapper, including its ApiError type check.
  const source=requirements.match(/function adjustmentErrorCode[\s\S]*?\nfunction DailyRequirementTable/)?.[0].replace(/\nfunction DailyRequirementTable$/,'')
  assert.ok(source)
  class ApiError extends Error { constructor(detail){super('API failed');this.detail=detail} }
  const context={ApiError}
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,context)
  assert.match(context.requirementErrorMessage(new ApiError({code:'ADJUSTMENT_COVERAGE_CONFLICT'})),/重疊的確認範圍.*請只選擇一個有效來源/)
  assert.match(context.requirementErrorMessage(new ApiError({code:'ADJUSTMENT_COVERAGE_UNAVAILABLE'})),/歷史範圍資料不完整.*已停止計算.*勿以最新菜單代替/)
})
