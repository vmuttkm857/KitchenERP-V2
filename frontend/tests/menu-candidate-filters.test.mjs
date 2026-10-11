import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {menuMonthRange} from '../src/features/menus/menuCandidateFilterUtils.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const filters=read('../src/features/menus/MenuCandidateFilters.tsx')
const hook=read('../src/features/menus/useMenuCandidates.ts')
const adjustments=read('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx')
const requirements=read('../src/features/requirements/RequirementsPage.tsx')
const css=read('../src/styles/global.css')
const pagination=read('../src/components/ui/PaginationControls.tsx')

test('menu month filter produces an inclusive calendar-month overlap range',()=>{
  assert.deepEqual(menuMonthRange('2026-09'),{startDate:'2026-09-01',endDate:'2026-09-30'})
  assert.deepEqual(menuMonthRange('2028-02'),{startDate:'2028-02-01',endDate:'2028-02-29'})
  assert.deepEqual(menuMonthRange(''),{startDate:undefined,endDate:undefined})
})

test('shared filters use real menu categories and combine month category and name server-side',()=>{
  assert.match(filters,/type="month"/)
  assert.match(filters,/全部日期/)
  assert.match(filters,/全部類型/)
  assert.match(filters,/\/categories\/menu\?active=true&page_size=100/)
  assert.match(filters,/清除篩選/)
  assert.match(hook,/categoryId/)
  assert.match(hook,/buildListQuery\(\{page,pageSize,search:debouncedSearch,active,categoryId,startDate,endDate\}\)/)
})

test('both selectors share filters while selections and work dates remain independent',()=>{
  for(const source of [adjustments,requirements]){
    assert.match(source,/MenuCandidateFilters/)
    assert.match(source,/menuMonthRange\(menuMonth\)/)
    assert.match(source,/menu-selection-chip/)
    assert.match(source,/已選 \{/)
  }
  assert.match(adjustments,/setStartDate\(event\.target\.value\);setDatesTouched\(true\)/)
  assert.match(requirements,/決定實際需求量計算期間，與上方菜單月份篩選互不影響/)
  assert.doesNotMatch(filters,/startDate|endDate|setStartDate|setEndDate/)
})

test('filter and pagination presentation stays compact without vertical word wrapping',()=>{
  assert.match(css,/\.menu-candidate-filter-panel\{[^}]*display:grid/)
  assert.match(pagination,/className="pagination-jump-fields"/)
  assert.match(css,/\.pagination-jump-fields\{[^}]*display:flex[^}]*white-space:nowrap/)
  assert.match(css,/\.pagination-jump\{display:block;flex:none\}/)
  assert.match(css,/@media\(max-width:560px\)\{\.menu-candidate-filter-panel\{grid-template-columns:1fr\}/)
  assert.match(css,/\.pagination-pages,.pagination-jump\{width:100%\}/)
})

test('both pages share a two-level menu option with aligned checkbox and responsive layout',()=>{
  assert.match(filters,/export function MenuCandidateOption/)
  assert.match(filters,/menu-candidate-name/)
  assert.match(filters,/menu-candidate-meta/)
  assert.match(filters,/menu\.category_name\|\|'未分類'/)
  assert.match(filters,/menu\.start_date\}～\{menu\.end_date/)
  assert.match(adjustments,/MenuCandidateOption key=\{menu\.id\}/)
  assert.match(requirements,/MenuCandidateOption key=\{menu\.id\}/)
  assert.match(css,/\.menu-candidate-option\{[^}]*grid-template-columns:auto minmax\(0,1fr\)/)
  assert.match(css,/\.menu-candidate-name\{[^}]*overflow-wrap:anywhere/)
})

test('requirements conditions use a 65/35 desktop split with stacked right-side sections',()=>{
  assert.match(requirements,/menu-selection-step/)
  assert.match(requirements,/date-range-step/)
  assert.match(css,/\.requirements-page \.calculation-workflow\{grid-template-columns:minmax\(0,65fr\) minmax\(18rem,35fr\)/)
  assert.match(css,/\.requirements-page \.menu-selection-step\{grid-column:1;grid-row:1\/span 2/)
  assert.match(css,/\.requirements-page \.date-range-step\{grid-column:2;grid-row:1/)
  assert.match(css,/\.requirements-page \.quantity-basis-step\{grid-column:2;grid-row:2/)
  assert.match(css,/\.requirements-page \.workflow-submit\{grid-column:1\/-1;grid-row:3\}/)
  assert.match(css,/@media\(max-width:1180px\)\{\.requirements-page \.calculation-workflow\{grid-template-columns:minmax\(0,1fr\)/)
})

test('requirements menu list shows five normal rows and keeps pagination outside the scroller',()=>{
  assert.match(css,/\.requirements-page \.menu-selection-step \.menu-choices\{height:calc\(5 \* 4\.25rem \+ 4 \* \.4rem\);max-height:none;overflow-y:auto/)
  assert.match(css,/grid-auto-rows:minmax\(4\.25rem,max-content\)/)
  assert.match(css,/\.requirements-page \.menu-candidate-option\{min-height:4\.25rem/)
  assert.match(requirements,/<\/div>\{!menuCandidates\.loading[\s\S]*?<PaginationControls/)
})
