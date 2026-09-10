import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumMenuSourcePage.tsx',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const stateSource=readFileSync(new URL('../src/features/postpartum/menuSourceTypes.ts',import.meta.url),'utf8')
const candidatesSource=readFileSync(new URL('../src/features/menus/useMenuCandidates.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(stateSource,{compilerOptions:{module:ts.ModuleKind.ES2022}}).outputText
const state=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const meals=[
  {value:'breakfast'},{value:'morning_snack'},{value:'lunch'},
  {value:'afternoon_snack'},{value:'dinner'},{value:'evening_snack'},
]

function source(id,start,end,{active=true,warnings=[]}={}){
  return {id,configured:true,usable:true,menu:{id:`menu-${id}`,name:`菜單 ${id}`,start_date:start,end_date:end,is_active:active},mappings:[],meal_statuses:[],warnings}
}

test('navigation and page expose multiple menu sources and coverage',()=>{
  assert.match(app,/菜單來源／週期/)
  assert.match(page,/月子餐菜單來源／週期覆蓋/)
  assert.match(page,/listSources\.map/)
  assert.match(page,/新增菜單來源/)
  assert.match(page,/編輯/)
})

test('six canonical rows allow unmapped values and save only selected mappings',()=>{
  assert.match(page,/POSTPARTUM_MEALS\.map/)
  assert.match(page,/<option value="">未設定<\/option>/)
  assert.match(page,/\.filter\(item=>Boolean\(mappings\[item\.value\]\)\)/)
  const mapping=state.emptyMenuMappings(meals)
  assert.equal(state.menuMappingsValid(mapping),false)
  mapping.breakfast='erp-breakfast'
  assert.equal(state.menuMappingsValid(mapping),true)
  mapping.lunch='erp-breakfast'
  assert.equal(state.menuMappingsValid(mapping),false)
  assert.equal(state.mealTypeUsedByOtherMeal(mapping,'breakfast','erp-breakfast'),true)
})

test('month coverage dynamically renders five or six calendar-week segments',()=>{
  const september=state.buildMonthWeekSegments([],'2026-09')
  assert.deepEqual(september.map(item=>[item.start_date,item.end_date]),[
    ['2026-09-01','2026-09-06'],['2026-09-07','2026-09-13'],
    ['2026-09-14','2026-09-20'],['2026-09-21','2026-09-27'],['2026-09-28','2026-09-30'],
  ])
  assert.equal(state.buildMonthWeekSegments([],'2026-08').length,6)
})

test('one source spanning two weeks covers both and overlap remains explicit',()=>{
  const spanning=source('spanning','2026-09-07','2026-09-20')
  const periods=state.buildMonthWeekSegments([spanning],'2026-09')
  assert.equal(periods[1].status,'configured')
  assert.equal(periods[2].status,'configured')
  const overlapping=state.buildMonthWeekSegments([
    source('a','2026-09-07','2026-09-13'),
    source('b','2026-09-10','2026-09-20',{warnings:[{code:'SOURCE_DATE_OVERLAP'}]}),
  ],'2026-09')
  assert.equal(overlapping[1].status,'overlap')
  assert.match(page,/source\.warnings\.map/)
  assert.match(page,/日期重疊/)
})

test('coverage and configured-source month controls are independent and query server ranges',()=>{
  assert.match(page,/\[coverageMonth,setCoverageMonth\]=useState\(currentMonth\)/)
  assert.match(page,/\[listMonth,setListMonth\]=useState\(currentMonth\)/)
  assert.match(page,/label="週期覆蓋月份" value=\{coverageMonth\} onChange=\{setCoverageMonth\}/)
  assert.match(page,/label="已設定來源月份" value=\{listMonth\} onChange=\{setListMonth\}/)
  assert.match(page,/from_date=\$\{range\.start_date\}&to_date=\$\{range\.end_date\}/)
  assert.match(page,/input type="month"/)
  assert.equal(state.nextMonthValue('2026-12'),'2027-01')
  assert.deepEqual(state.monthRange('2030-12'),{start_date:'2030-12-01',end_date:'2030-12-31'})
})

test('dialog month defaults follow coverage week general create and edited source',()=>{
  assert.match(page,/function openCreate\(month=coverageMonth\)/)
  assert.match(page,/openCreate\(period\.start_date\.slice\(0,7\)\)/)
  assert.match(page,/setDialogMonth\(source\.menu\.start_date\.slice\(0,7\)\)/)
  assert.equal(state.buildMonthWeekSegments([],'2027-05')[0].start_date.slice(0,7),'2027-05')
  assert.equal(state.buildMonthWeekSegments([],'2026-09')[2].start_date.slice(0,7),'2026-09')
})

test('dialog menu candidates combine arbitrary month name search and server pagination',()=>{
  assert.match(page,/label="ERP 菜單候選月份" value=\{dialogMonth\}/)
  assert.match(page,/startDate:dialogRange\.start_date,endDate:dialogRange\.end_date/)
  assert.match(page,/changeCandidateSearch\(event\.target\.value\)/)
  assert.match(page,/onPage=\{changeCandidatePage\}/)
  assert.match(page,/此月份沒有符合條件的 ERP 菜單/)
  assert.match(candidatesSource,/buildListQuery\(\{page,pageSize,search:debouncedSearch,active,startDate,endDate\}\)/)
  assert.match(candidatesSource,/useEffect\(\(\)=>setPage\(1\),\[active,debouncedSearch,startDate,endDate\]\)/)
  assert.match(candidatesSource,/RequestSequence/)
  assert.match(candidatesSource,/sequence\.current\.isCurrent\(request\)/)
})

test('dialog month selector supports current next and historical or future custom months',()=>{
  assert.match(page,/>當月<\/button>/)
  assert.match(page,/>下個月<\/button>/)
  assert.match(page,/input type="month"/)
  assert.deepEqual(state.monthRange('2027-05'),{start_date:'2027-05-01',end_date:'2027-05-31'})
  assert.deepEqual(state.monthRange('2030-12'),{start_date:'2030-12-01',end_date:'2030-12-31'})
})

test('filtered source list has its own loading and empty states',()=>{
  assert.match(page,/已設定菜單來源載入中/)
  assert.match(page,/此月份尚無已設定菜單來源/)
  assert.match(page,/只顯示與所選月份有交集的來源/)
})

test('persisted inactive menu and meal types remain visible with warnings',()=>{
  assert.match(page,/values\.unshift\(selectedMenuSnapshot\)/)
  assert.match(page,/meal\.is_active\|\|meal\.id===mappings\[item\.value\]/)
  assert.match(page,/（已停用）/)
  assert.match(page,/source\.warnings\.map/)
})

test('loading error success and POST PUT paths are explicit',()=>{
  assert.match(page,/週期覆蓋載入中/)
  assert.match(page,/週期覆蓋載入失敗/)
  assert.match(page,/菜單來源設定已儲存/)
  assert.match(page,/method:editingSource\?'PUT':'POST'/)
  assert.match(page,/await Promise\.all\(\[loadCoverageSources\(\),loadListSources\(\)\]\)/)
})
