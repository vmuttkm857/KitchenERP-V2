import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumCasesPage.tsx',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const timeline=readFileSync(new URL('../src/features/postpartum/timeline.ts',import.meta.url),'utf8')
const compiledTimeline=ts.transpileModule(timeline,{compilerOptions:{module:ts.ModuleKind.ES2022}}).outputText
const timelineModule=await import(`data:text/javascript;base64,${Buffer.from(compiledTimeline).toString('base64')}`)

test('postpartum navigation and case management are wired',()=>{
  assert.match(app,/月子餐/);assert.match(app,/PostpartumCasesPage/)
  for(const label of ['號碼','房號／床號','生產方式','起伙日期','調理方式','房號歷程','暫停服務紀錄']) assert.match(page,new RegExp(label))
  assert.match(page,/\/postpartum\/cases/)
})

test('date-only week ranges start on delivery day without local timezone conversion',()=>{
  assert.match(timeline,/Date\.UTC/)
  assert.match(timeline,/start\+index\*7\*dayMilliseconds/)
  assert.match(timeline,/index\*7\+6/)
  assert.match(timeline,/days>=28/)
  assert.doesNotMatch(timeline,/T00:00:00/)
  assert.deepEqual(timelineModule.postpartumWeekRanges('2026-09-08'),[
    {week:1,from:'2026-09-08',to:'2026-09-14'},
    {week:2,from:'2026-09-15',to:'2026-09-21'},
    {week:3,from:'2026-09-22',to:'2026-09-28'},
    {week:4,from:'2026-09-29',to:'2026-10-05'},
  ])
  const atDay=day=>new Date(2026,8,8+day,12)
  assert.equal(timelineModule.postpartumWeek('2026-09-08',atDay(0)),'第 1 週')
  assert.equal(timelineModule.postpartumWeek('2026-09-08',atDay(6)),'第 1 週')
  assert.equal(timelineModule.postpartumWeek('2026-09-08',atDay(7)),'第 2 週')
  assert.equal(timelineModule.postpartumWeek('2026-09-08',atDay(27)),'第 4 週')
  assert.equal(timelineModule.postpartumWeek('2026-09-08',atDay(28)),'第 4 週後')
})

test('edit modal owns separate state and cannot patch current room',()=>{
  assert.match(page,/createForm,setCreateForm/)
  assert.match(page,/editingCase,setEditingCase/)
  assert.match(page,/editForm,setEditForm/)
  assert.match(page,/修改月子餐個案/)
  assert.match(page,/function closeEdit\(\)\{setEditingCase\(null\);setEditForm\(null\)/)
  assert.match(page,/const \{current_room,\.\.\.payload\}=payloadFrom\(editForm\)/)
  assert.doesNotMatch(page,/closeEdit\(\).*setCreateForm/)
})

test('optional service end clears meal and renders 未定',()=>{
  assert.match(page,/service_end_date:form\.service_end_date\|\|null/)
  assert.match(page,/service_end_meal:form\.service_end_date\?/)
  assert.match(page,/disabled=\{!form\.service_end_date\}/)
  assert.match(page,/'未定'/)
})

test('room change refreshes both detail and list current room',()=>{
  assert.match(page,/await refreshDetail\(detail\.case\.id\);await load\(\)/)
  assert.match(page,/異動日期/)
  assert.match(page,/異動餐別/)
  assert.doesNotMatch(page,/max=\{localToday\(\)\}/)
  assert.doesNotMatch(page,/roomDate>localToday\(\)/)
  assert.doesNotMatch(page,/異動日期不可晚於今天/)
})
