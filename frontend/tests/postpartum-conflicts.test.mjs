import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumConflictPage.tsx',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const typeSource=readFileSync(new URL('../src/features/postpartum/conflictTypes.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(typeSource,{compilerOptions:{module:ts.ModuleKind.ES2022}}).outputText
const helpers=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

function summary(status,values={}){
  return {status,conflict_case_count:0,conflict_count:0,manual_review_case_count:0,...values}
}

test('navigation exposes the daily-first postpartum conflict overview',()=>{
  assert.match(app,/PostpartumConflictPage/)
  assert.match(app,/postpartum-conflicts/)
  assert.match(app,/禁忌總覽/)
  assert.match(page,/月子餐禁忌總覽/)
  assert.match(page,/useState<ViewMode>\('daily'\)/)
  assert.match(page,/日檢視/)
  assert.match(page,/週檢視/)
})

test('daily navigation uses Taipei today and loads all six meals in one request',()=>{
  assert.equal(helpers.todayTaipeiYmd(new Date('2026-09-09T16:30:00Z')),'2026-09-10')
  assert.equal(helpers.addYmdDays('2026-09-10',-1),'2026-09-09')
  assert.match(page,/前一天/)
  assert.match(page,/今天/)
  assert.match(page,/下一天/)
  assert.match(page,/\/postpartum\/menu-conflicts\/daily\?/) 
  assert.match(page,/target_date:targetDate/)
  assert.doesNotMatch(page,/postpartum_meal:meal/)
  assert.match(page,/data\.summaries\.map/)
})

test('summary labels distinguish conflict partial complete unmapped and unavailable',()=>{
  assert.equal(helpers.summaryLabel(summary('conflict',{conflict_case_count:2,conflict_count:6})),'🔴 2人・6項')
  assert.equal(helpers.summaryLabel(summary('partial',{manual_review_case_count:1})),'⚠ 1人')
  assert.equal(helpers.summaryLabel(summary('complete')),'✓')
  assert.equal(helpers.summaryLabel(summary('unmapped')),'—')
  assert.equal(helpers.summaryLabel(summary('unavailable')),'⚠ 無法檢查')
  assert.match(page,/SummaryBadge/)
  assert.match(page,/StatusMark/)
  assert.match(page,/postpartum-conflict-status-mark/)
  assert.match(page,/effectiveCaseCount/)
  assert.match(page,/有效個案/)
})

test('daily case cards stay compact until details are requested',()=>{
  assert.match(page,/buildDailyCases/)
  assert.match(page,/個案禁忌總覽/)
  assert.match(page,/current_room/)
  assert.match(page,/case_number/)
  assert.match(page,/restriction_groups\.map/)
  assert.match(page,/查看詳情/)
  assert.match(page,/收合詳情/)
  assert.match(page,/aria-expanded/)
  assert.match(page,/expanded&&/)
  assert.match(page,/GroupedReasons/)
  assert.match(page,/菜色命中/)
  assert.match(page,/食材：/)
  assert.match(page,/配方資料不足/)
  assert.match(page,/未發現衝突/)
  assert.match(page,/noteworthy/)
  assert.match(page,/MealFilter='all'\|Meal/)
  assert.match(page,/onChoose\('all'\)/)
  assert.doesNotMatch(page,/postpartum-conflict-matrix/)
})

test('unmapped and unavailable meals retain contextual non-safe messages',()=>{
  const unavailable=(sourceStatus,mappingStatus,warnings=[])=>({source_resolution:{status:sourceStatus,source:null,candidates:[]},mapping_resolution:{status:mappingStatus,menu_meal_type:null},warnings})
  assert.equal(helpers.unavailableMessage(unavailable('available','not_mapped')),'本餐未設定 ERP 菜單對應，因此未執行禁忌檢查。')
  assert.equal(helpers.unavailableMessage(unavailable('not_configured','not_checked')),'該日期尚未設定月子餐 ERP 菜單來源。')
  assert.equal(helpers.unavailableMessage(unavailable('ambiguous','not_checked')),'該日期有多個月子餐菜單來源，為避免誤判，未執行禁忌檢查。')
  assert.match(page,/MealNotices/)
  assert.match(page,/mapping_resolution\.status!=='not_mapped'/)
  assert.match(page,/const grouped=new Map/)
  assert.match(page,/item\.labels\.join\('、'\)/)
})

test('weekly view is a seven by six summary and cell navigation opens highlighted daily view',()=>{
  assert.match(page,/\/postpartum\/menu-conflicts\/weekly\?/)
  assert.match(page,/anchor_date:targetDate/)
  assert.match(page,/上一週/)
  assert.match(page,/本週/)
  assert.match(page,/下一週/)
  assert.match(page,/data\.days\.map/)
  assert.match(page,/POSTPARTUM_MEALS\.map/)
  assert.match(page,/day\.meals\.map/)
  assert.match(page,/function openDay\(date:string,meal:Meal\)/)
  assert.match(page,/setMealFilter\(meal\)/)
  assert.match(page,/setView\('daily'\)/)
  assert.match(page,/is-highlighted/)
  assert.equal(helpers.formatWeekDate('2026-09-07'),'09/07（一）')
  assert.match(page,/is-today/)
  assert.match(page,/>今天</)
})

test('daily and weekly requests protect against stale responses and show loading errors and empty cases',()=>{
  assert.match(page,/requestSequence=useRef\(0\)/)
  assert.match(page,/request!==requestSequence\.current/)
  assert.match(page,/request===requestSequence\.current/)
  assert.match(page,/return \(\)=>\{requestSequence\.current\+=1\}/)
  assert.match(page,/禁忌總覽載入中/)
  assert.match(page,/禁忌總覽載入失敗/)
  assert.match(page,/沒有符合供餐資格的月子餐個案/)
})
