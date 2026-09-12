import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const page=readFileSync(new URL('../src/features/postpartum/PostpartumChangeSheetPage.tsx',import.meta.url),'utf8')
const types=readFileSync(new URL('../src/features/postpartum/changeSheetTypes.ts',import.meta.url),'utf8')
const css=readFileSync(new URL('../src/features/postpartum/PostpartumChangeSheetPage.css',import.meta.url),'utf8')
const client=readFileSync(new URL('../src/api/client.ts',import.meta.url),'utf8')

test('daily change sheet navigation remains read-only',()=>{
  assert.match(app,/PostpartumChangeSheetPage/);assert.match(app,/postpartum-change-sheet/);assert.match(app,/每日異動單/)
  assert.match(page,/月子餐每日異動單/);assert.match(page,/前往禁忌總覽處理/)
  assert.doesNotMatch(page,/method:'(?:POST|PUT|PATCH|DELETE)'/)
})

test('Word export uses the authenticated download helper for the selected date',()=>{
  assert.match(page,/apiDownload/)
  assert.match(page,/\/postpartum\/change-sheet\/daily\.docx\?\$\{new URLSearchParams\(\{target_date:targetDate\}\)\}/)
  assert.doesNotMatch(page,/daily\.docx[^`]*postpartum_meal/)
  assert.match(page,/exportingWord\?'匯出中…':'匯出 Word'/)
  assert.match(page,/disabled=\{exportingWord\}/)
  assert.match(page,/Word 異動單匯出失敗/)
  assert.match(client,/if \(!response\.ok\) throw new Error\(`Download failed with status/)
  assert.match(client,/Content-Disposition/)
  assert.match(client,/response\.blob\(\)/)
  assert.match(client,/anchor\.download = filename/)
  assert.match(client,/document\.body\.appendChild\(anchor\)/)
  assert.match(client,/anchor\.remove\(\)/)
  assert.match(client,/window\.setTimeout\(\(\) => URL\.revokeObjectURL\(url\), 0\)/)
})

test('Word export state cannot replace or reload the daily preview',()=>{
  const handler=page.match(/async function exportWord\(\)\{([\s\S]*?)\n  \}/)?.[1]??''
  assert.match(handler,/setExportingWord\(true\)/)
  assert.match(handler,/finally\{setExportingWord\(false\)\}/)
  for(const forbidden of ['setLoading(', 'setData(', 'setTargetDate(', 'requestSequence'])assert.doesNotMatch(handler,new RegExp(forbidden.replace('(','\\(')))
  assert.match(page,/loading\?<div className="state-panel"/)
  assert.match(page,/data&&<>/)
})

test('one date request loads the authoritative daily endpoint with stale protection',()=>{
  assert.match(page,/useState\(todayTaipeiYmd\)/)
  assert.match(page,/\/postpartum\/change-sheet\/daily\?\$\{query\}/)
  assert.match(page,/new URLSearchParams\(\{target_date:targetDate\}\)/)
  assert.doesNotMatch(page,/postpartum_meal:meal/);assert.doesNotMatch(page,/setMeal/)
  assert.match(page,/requestSequence\.current/);assert.match(page,/request===requestSequence\.current/)
  for(const text of ['前一天','今天','下一天','type="date"'])assert.match(page,new RegExp(text))
})

test('daily response types preserve backend summary meals and canonical server order',()=>{
  assert.match(types,/interface ChangeSheetDailyResponse/)
  for(const token of ['target_date:string','summary:ChangeSheetSummary','meals:ChangeSheetMealResponse\\[\\]','has_changes:boolean'])assert.match(types,new RegExp(token))
  assert.match(page,/data\.meals\.map\(meal=><MealSection/)
  assert.doesNotMatch(page,/\.sort\(/)
})

test('empty meals are compact while changed meals render work sections',()=>{
  assert.match(page,/if\(!meal\.has_changes\)return <section className="postpartum-change-meal-empty"/)
  assert.match(page,/\{meal\.meal_label\}<\/strong><span>無異動/)
  assert.match(page,/className="postpartum-change-meal"/)
  assert.doesNotMatch(page,/本餐沒有替代菜製作項目/)
  assert.doesNotMatch(page,/本餐沒有人工確認不需替代項目/)
  assert.match(css,/postpartum-change-meal-empty\{display:flex/)
})

test('kitchen production uses backend quantity and rooms directly',()=>{
  assert.match(page,/廚房製作/);assert.match(page,/\{group\.quantity\} 份/)
  assert.doesNotMatch(page,/case_rooms\.length.*份/)
  assert.match(page,/group\.case_rooms\.join\('、'\)/)
  assert.match(page,/此替代內容尚需營養師重新確認/)
})

test('case detail is one table-like row per handling item without dedupe',()=>{
  assert.match(page,/個案異動/);assert.match(page,/postpartum-change-detail-head/);assert.match(page,/postpartum-change-detail-row/)
  assert.match(page,/meal\.replacement_groups\.flatMap\(group=>group\.items\.map/)
  assert.doesNotMatch(page,/new Map.*group\.items/)
  for(const token of ['current_room','case_name','original_dish\\.name','replacement_dish\\.name','RestrictionBadges'])assert.match(page,new RegExp(token))
  assert.match(page,/>→</)
  assert.match(css,/grid-template-columns:minmax\(4rem/)
})

test('acknowledgements and flattened stale items stay inside their meal',()=>{
  assert.match(page,/meal\.manual_acknowledgements\.length>0/)
  assert.match(page,/meal\.manual_acknowledgements\.map/)
  assert.match(page,/人工確認｜不需替代/);assert.match(page,/item\.note\|\|'—'/)
  assert.match(page,/meal\.requires_reconfirmation\.length>0/)
  assert.match(page,/meal\.requires_reconfirmation\.map/)
  assert.match(page,/今日共有 \{data\.summary\.requires_reconfirmation_count\} 項異動需要重新確認/)
  assert.match(page,/meal\.requires_reconfirmation\.map\(item=><ReconfirmationItem/)
})

test('warning details stay collapsed and states avoid raw enum labels',()=>{
  assert.match(page,/<details className="postpartum-change-warning-details">/)
  assert.match(page,/new Set\(items\.map\(item=>item\.message\)/)
  for(const text of ['已設定替代','人工確認｜不需替代','待重新確認'])assert.match(page,new RegExp(text))
  assert.doesNotMatch(page,/>replaced</);assert.doesNotMatch(page,/>manually_acknowledged</);assert.doesNotMatch(page,/>requires_reconfirmation</)
})

test('warning detail triggers render only for non-empty backend warnings',()=>{
  assert.match(page,/if\(messages\.length===0\)return null/)
  assert.match(page,/group\.warnings\.length>0&&<WarningDetails items=\{group\.warnings\}/)
  assert.match(page,/item\.warnings\.length>0&&<WarningDetails items=\{item\.warnings\}/)
  assert.match(page,/meal\.warnings\.length>0&&<WarningDetails items=\{meal\.warnings\}/)
})

test('stale acknowledgement stays one handling while technical detail is shown only below',()=>{
  assert.match(page,/data-handling-id=\{item\.handling_id\}/)
  assert.match(page,/stale\?'⚠ 待重新確認':'不需替代'/)
  assert.match(page,/!stale&&item\.warnings\.length>0&&<WarningDetails items=\{item\.warnings\}/)
  assert.match(page,/function ReconfirmationItem[\s\S]*item\.warnings\.length>0&&<WarningDetails items=\{item\.warnings\}/)
  assert.match(page,/meal\.manual_acknowledgements\.map\(item=><AcknowledgementRow key=\{item\.handling_id\}/)
  assert.match(page,/meal\.requires_reconfirmation\.map\(item=><ReconfirmationItem key=\{`\$\{item\.handling_type\}-\$\{item\.handling_id\}`\}/)
})

test('loading error and empty-day states are explicit',()=>{
  for(const text of ['每日異動單載入中','每日異動單載入失敗','重新載入','今日六餐目前沒有月子餐異動'])assert.match(page,new RegExp(text))
  assert.match(page,/替代製作：\{data\.summary\.replacement_item_count\} 項/)
  assert.match(page,/人工確認：\{data\.summary\.manual_acknowledgement_count\} 項/)
  assert.match(page,/待重新確認：\{data\.summary\.requires_reconfirmation_count\} 項/)
  assert.doesNotMatch(page,/共同替代組：/)
})
