import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumCateringOverviewPage.tsx',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const css=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')

test('catering overview is a dedicated navigable page',()=>{
  assert.match(app,/postpartum-catering-overview/)
  assert.match(app,/供餐總覽/)
  assert.match(app,/PostpartumCateringOverviewPage/)
})

test('daily controls, readable table and empty state are present',()=>{
  for(const text of ['前一天','今天','下一天','供餐日期','床號','姓名','調理方式','起伙：','飲食禁忌／備註','本日無月子餐供餐個案'])assert.match(page,new RegExp(text))
  assert.match(page,/serviceMoment\(item\.service_start_date,item\.service_start_meal_label\)/)
  assert.doesNotMatch(page,/停伙：/)
  assert.doesNotMatch(page,/serviceMoment\(item\.service_end_date,item\.service_end_meal_label\)/)
  assert.match(page,/if\(!date\|\|!mealLabel\)return '—'/)
  assert.doesNotMatch(page,/item\.case_number/)
  assert.equal((page.match(/<th>/g)||[]).length,4)
  assert.match(page,/postpartum-catering-person/)
  assert.match(page,/postpartum-catering-combined/)
  assert.match(page,/restriction_groups\.map/)
  assert.match(page,/已停用/)
  assert.match(css,/postpartum-catering-restrictions[^}]*flex-wrap:wrap/)
  assert.match(css,/postpartum-catering-restrictions>span[^}]*color:#8d2424/)
  assert.match(css,/postpartum-catering-person>strong\+small[^}]*border-top/)
  assert.match(css,/postpartum-catering-note[^}]*color:#1f4e79/)
  assert.match(css,/postpartum-catering-note[^}]*font-weight:700/)
  assert.match(css,/postpartum-catering-note[^}]*white-space:pre-wrap/)
})

test('preview and Word export keep independent loading states',()=>{
  assert.match(page,/\[loading,setLoading\]/)
  assert.match(page,/\[exporting,setExporting\]/)
  assert.match(page,/apiDownload\(`\/postpartum\/catering-overview\.docx/)
  assert.match(page,/finally\{setExporting\(false\)\}/)
  assert.doesNotMatch(page,/function exportWord\(\)[\s\S]{0,250}setLoading/)
})

test('stale daily responses cannot replace a newer date',()=>{
  assert.match(page,/requestSequence=useRef\(0\)/)
  assert.match(page,/request===requestSequence\.current/)
  assert.match(page,/return\(\)=>\{requestSequence\.current\+=1\}/)
})
