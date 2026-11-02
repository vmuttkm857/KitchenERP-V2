import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import {menuImportDates,menuImportGridRows,menuImportStatus} from '../src/features/menus/menuImportGrid.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const dialog=read('../src/features/menus/MenuImportDialog.tsx')
const review=read('../src/features/menus/MenuImportReviewPage.tsx')
const grid=read('../src/features/menus/MenuImportWeekGrid.tsx')
const menus=read('../src/features/menus/MenusPage.tsx')
const app=read('../src/app/App.tsx')
const picker=read('../src/features/menus/DishSearchPicker.tsx')
const css=read('../src/styles/global.css')
const line=(date,meal,mealOrder,column,columnOrder,name,reviewRequired=false)=>({
  line_key:`${date}-${meal}-${column}`,date,meal_name:meal,meal_sort_order:mealOrder,column_name:column,column_sort_order:columnOrder,
  original_import_name:name,normalized_name:name,dish:reviewRequired?null:{id:name,code:name,name,is_active:true},status:reviewRequired?'UNMATCHED':'MATCHED',review_required:reviewRequired,source_row:2,source_column:3,diner_count:1,
})

// Real dialog callbacks and controlled promises; not React DOM/browser E2E.
function resolutionHarness(excluded=false){
  let hooks=[],cursor=0,effects=[],cleanups=[],tree
  const calls=[],resolved=[],Picker=()=>{},pending={}
  pending.promise=new Promise((resolve,reject)=>Object.assign(pending,{resolve,reject}))
  const react={
    useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=typeof initial==='function'?initial():initial;return [hooks[i],value=>{hooks[i]=typeof value==='function'?value(hooks[i]):value}]},
    useRef(initial){const i=cursor++;return hooks[i]??=( {current:initial} )},
    useEffect(fn,deps){const i=cursor++;if(!hooks[i]||deps.some((v,j)=>v!==hooks[i][j])){hooks[i]=deps;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn()})}},
  }
  const jsx=(type,props)=>({type,props}),exports={}
  vm.runInNewContext(ts.transpileModule(review+'\nexport { DishResolutionDialog };',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
    exports,window:{setTimeout(){return 1},clearTimeout(){}},require:p=>p==='react'?react:p==='react/jsx-runtime'?{jsx,jsxs:jsx}:p==='../../api/client'?{ApiError:class extends Error{},apiRequest:(path,init)=>{calls.push({path,init});if(path.startsWith('/categories/'))return Promise.resolve({items:[]});if(!init)throw Error('Unexpected GET after mutation');return pending.promise}}:p==='./DishSearchPicker'?{DishSearchPicker:Picker}:p==='./menuImportGrid'?{menuImportStatus:x=>x.resolution_status}:{}
  })
  const props={batchId:'batch',line:{id:'line',date:'2026-11-09',meal_name:'午餐',column_name:'主菜',original_import_name:'原菜名',resolution_status:excluded?'EXCLUDED':'UNMATCHED'},onClose(){},onResolved:value=>resolved.push(value)}
  function render(){cursor=0;effects=[];tree=exports.DishResolutionDialog(props);effects.forEach(fn=>fn())}
  const nodes=x=>Array.isArray(x)?x.flatMap(nodes):x&&typeof x==='object'?[x,...nodes(x.props?.children)]:[]
  const text=x=>Array.isArray(x)?x.map(text).join(''):x&&typeof x==='object'?text(x.props?.children):typeof x==='string'?x:''
  render()
  return {calls,resolved,pending,render,unmount(){cleanups.forEach(fn=>fn?.())},button:label=>nodes(tree).find(n=>n.type==='button'&&text(n)===label),texts:()=>text(tree),choose(){nodes(tree).find(n=>n.type===Picker).props.onAdd({id:'dish',name:'測試菜色',code:'D'});render()},writes:()=>calls.filter(c=>c.init?.method),gets:()=>calls.filter(c=>!c.init?.method&&!c.path.startsWith('/categories/'))}
}

for(const action of ['resolve','exclude','restore']){
  test(`${action} applies the complete server response with one mutation and no follow-up GET`,async()=>{
    const ui=resolutionHarness(action==='restore');await Promise.resolve()
    if(action==='resolve')ui.choose()
    if(action==='exclude'){ui.button('從匯入排除').props.onClick();ui.render()}
    const label={resolve:'確認變更',exclude:'確定排除',restore:'恢復此菜色'}[action]
    const operation=ui.button(label).props.onClick();ui.render()
    assert.equal(ui.resolved.length,0);assert.equal(ui.writes().length,1)
    assert.equal(ui.writes()[0].init.method,action==='resolve'?'PATCH':'POST')
    assert.equal(ui.writes()[0].path,`/menu-imports/batch/lines/line${action==='resolve'?'':`/${action}`}`)
    assert.ok(ui.button('取消').props.disabled)
    const response={id:'batch',status:'REVIEW_REQUIRED',can_finalize:false,summary:{duplicate_conflict_count:2,review_required_count:2,excluded_count:1},lines:[{id:'line',resolution_status:'MANUALLY_RESOLVED',duplicate_conflict:true},{id:'other',resolution_status:'AMBIGUOUS'},{id:'third',resolution_status:'UNMATCHED'},{id:'excluded',resolution_status:'EXCLUDED'}],layout:[{column_name:'主菜'}],finalize_warnings:['重複菜色']}
    ui.pending.resolve(response);await operation;for(let i=0;i<6;i++)await Promise.resolve();ui.render()
    assert.equal(ui.resolved.length,1);assert.equal(ui.resolved[0],response)
    assert.equal(ui.gets().length,0);assert.equal(ui.button('取消').props.disabled,false)
    assert.ok(!ui.texts().includes('失敗'))
  })
}

test('READY response is retained exactly and same-tick duplicate actions submit only once',async()=>{
  const ui=resolutionHarness();ui.choose();const submit=ui.button('確認變更').props.onClick
  submit();submit();assert.equal(ui.writes().length,1)
  const response={id:'batch',status:'READY',can_finalize:true,summary:{duplicate_conflict_count:0,review_required_count:0},lines:[]}
  ui.pending.resolve(response);for(let i=0;i<8;i++)await Promise.resolve()
  assert.equal(ui.resolved.length,1);assert.equal(ui.resolved[0],response)
})

for(const action of ['resolve','exclude','restore'])test(`${action} failure keeps current draft and permits retry`,async()=>{
  const ui=resolutionHarness(action==='restore');if(action==='resolve')ui.choose()
  if(action==='exclude'){ui.button('從匯入排除').props.onClick();ui.render()}
  ui.button({resolve:'確認變更',exclude:'確定排除',restore:'恢復此菜色'}[action]).props.onClick()
  ui.pending.reject(Error('request failed'));for(let i=0;i<8;i++)await Promise.resolve();ui.render()
  assert.equal(ui.resolved.length,0);assert.equal(ui.gets().length,0)
  assert.ok(ui.texts().includes('失敗'));assert.equal(ui.button('取消').props.disabled,false)
  ui.button({resolve:'確認變更',exclude:'確定排除',restore:'恢復此菜色'}[action]).props.onClick()
  for(let i=0;i<8;i++)await Promise.resolve()
  assert.equal(ui.writes().length,2);assert.equal(ui.resolved.length,0)
})

test('a late mutation response from a closed dialog cannot update the draft',async()=>{
  const ui=resolutionHarness();ui.choose();ui.button('確認變更').props.onClick();ui.unmount()
  ui.pending.resolve({id:'batch',status:'READY'});for(let i=0;i<8;i++)await Promise.resolve()
  assert.equal(ui.resolved.length,0);assert.equal(ui.gets().length,0)
})

test('weekly planner uses the imported date range and backend meal/column sort order',()=>{
  const dates=menuImportDates('2026-10-05','2026-10-11')
  assert.equal(dates.length,7)
  const rows=menuImportGridRows([
    line('2026-10-06','午餐',2,'副菜',2,'B'),line('2026-10-05','早餐',1,'主菜',1,'A'),line('2026-10-05','午餐',2,'主菜',1,'C'),
  ],dates)
  assert.deepEqual(rows.map(row=>`${row.mealName}/${row.columnName}`),['早餐/主菜','午餐/主菜','午餐/副菜'])
  assert.equal(rows[1].cells[0]?.original_import_name,'C')
  assert.equal(rows[2].cells[1]?.original_import_name,'B')
})

test('layout metadata preserves configured rows that are blank for all seven days',()=>{
  const dates=menuImportDates('2026-10-05','2026-10-11')
  const layout=[
    {meal_name:'午餐',meal_sort_order:1,column_name:'主菜',column_sort_order:1},
    {meal_name:'午餐',meal_sort_order:1,column_name:'備菜3',column_sort_order:2},
  ]
  const rows=menuImportGridRows([line('2026-10-05','午餐',1,'主菜',1,'A')],dates,layout)
  assert.deepEqual(rows.map(row=>row.columnName),['主菜','備菜3'])
  assert.equal(rows[1].cells.every(cell=>cell===null),true)
})

test('upload is explicit xlsx preview then creates the draft from the same file and hash',()=>{
  assert.match(menus,/匯入 Excel/)
  assert.match(dialog,/accept="\.xlsx/)
  assert.match(dialog,/解析預覽/)
  assert.match(dialog,/\/menu-imports\/preview/)
  assert.match(dialog,/expected_source_hash/)
  assert.match(dialog,/preview\.source_hash/)
  assert.match(dialog,/建立匯入草稿/)
  assert.match(dialog,/preview\.layout/)
  assert.doesNotMatch(dialog,/preview\.lines.*JSON\.stringify/s)
})

test('preview exposes summary fatal overlap and review-required cells without mutating a menu',()=>{
  for(const text of ['需確認','日期與既有菜單重疊','無法建立草稿','建立匯入草稿'])assert.match(dialog,new RegExp(text))
  assert.match(grid,/if\(line\.review_required\)return'needs-review'/)
  assert.match(css,/\.menu-import-cell\.needs-review\{background:#fff1f2/)
  assert.doesNotMatch(dialog,/\/menus\/[^'`]*editor/)
})

test('duplicate draft and unfinished list both navigate to persistent review',()=>{
  assert.match(dialog,/MENU_IMPORT_DRAFT_EXISTS/)
  assert.match(dialog,/existing_batch_id/)
  assert.match(dialog,/繼續原草稿/)
  assert.match(dialog,/未完成的 Excel 匯入/)
  assert.match(app,/menu-import-review/)
  assert.match(app,/MenuImportReviewPage/)
})

test('review initially loads its authoritative batch and retains review states',()=>{
  assert.match(review,/apiRequest<MenuImportBatchDetail>\(`\/menu-imports\/\$\{batchId\}`\)/)
  assert.match(review,/method:'PATCH'/)
  assert.match(review,/dish_id:selected\.id/)
  assert.doesNotMatch(review,/setDetail\([^)]*review_required:\s*false/)
  assert.match(review,/菜單審核完成/)
  assert.match(review,/可以建立新的正式菜單/)
})

test('ready draft finalizes into a new menu and opens the existing menu editor',()=>{
  assert.match(review,/detail\.can_finalize&&<button[^>]*onClick=\{\(\)=>setFinalizeOpen\(true\)\}[^>]*>建立正式菜單/)
  assert.match(review,/defaultMenuName\(batch\.original_filename\)/)
  assert.match(review,/Excel 檔案/)
  assert.match(review,/已排除/)
  assert.match(review,/\/categories\/menu\?active=true&page_size=100/)
  assert.match(review,/start_date:batch\.start_date,end_date:batch\.end_date/)
  assert.match(review,/日期重疊僅供參考，不會覆蓋既有菜單/)
  assert.match(review,/不會修改或覆蓋其他既有菜單/)
  assert.match(review,/`\/menu-imports\/\$\{batch\.id\}\/finalize`/)
  assert.match(review,/method:'POST'/)
  assert.match(review,/category_id:categoryId\|\|null/)
  assert.match(review,/onOpenMenu\(result\.menu\)/)
  assert.match(review,/event\.key==='Escape'/)
  assert.match(review,/saving\|\|loadingInfo\|\|!name\.trim\(\)/)
  assert.match(review,/MENU_IMPORT_NOT_READY/)
  assert.match(app,/onOpenMenu=\{menu=>\{setEditingMenu\(menu\);navigate\('menu-editor'\)\}\}/)
})

test('finalized import history is read-only and can reopen its formal menu',()=>{
  assert.match(review,/detail\.status==='FINALIZED'/)
  assert.match(review,/onLine=\{finalized\?undefined:openReview\}/)
  assert.match(review,/!finalized&&<button[^>]*className="danger"/)
  assert.match(review,/已建立正式菜單/)
  assert.match(review,/匯入紀錄已鎖定/)
  assert.match(review,/apiRequest<Menu>\(`\/menus\/\$\{menuId\}`\)/)
  assert.match(css,/\.status-finalized/)
  assert.match(css,/\.menu-import-finalized-banner/)
})

test('dish correction reuses active paged dish search and keeps inactive candidates unavailable',()=>{
  assert.match(review,/active:'true'/)
  assert.match(review,/page_size:'20'/)
  assert.match(review,/DishSearchPicker/)
  assert.match(picker,/categories\.filter\(item => item\.is_active\)/)
  assert.match(review,/搜尋並選擇現有菜色/)
  assert.match(review,/草稿尚未變更/)
})

test('delete requires a dedicated confirmation and returns to menu management only on success',()=>{
  assert.match(review,/刪除匯入草稿/)
  assert.match(review,/確認刪除草稿/)
  assert.match(review,/method:'DELETE'/)
  assert.match(review,/await apiRequest\(`\/menu-imports\/\$\{batchId\}`/)
  assert.match(review,/onClose\(\)/)
})

test('review status comes from backend fields and imported diner count remains read-only',()=>{
  const draft={...line('2026-10-05','早餐',1,'主菜',1,'錯字',true),id:'line-1',resolution_status:'AMBIGUOUS',resolved_at:null,resolved_by:null,duplicate_conflict:false,excluded_at:null,excluded_by:null}
  assert.equal(menuImportStatus(draft),'AMBIGUOUS')
  assert.match(grid,/\{line\.diner_count\} 人/)
  assert.doesNotMatch(grid,/type="number"/)
  assert.match(review,/detail\.summary\.review_required_count/)
})

test('every persisted import line is editable while colors only communicate review state',()=>{
  assert.match(grid,/onClick=\{\(\)=>onLine\?\.\(line\)\}/)
  assert.match(grid,/disabled=\{!onLine\}/)
  assert.doesNotMatch(grid,/line\.review_required&&onLine/)
  assert.match(grid,/return'normal'/)
  assert.match(css,/\.menu-import-cell\.normal:not\(:disabled\):hover/)
  assert.match(grid,/menu-import-edit-hint/)
  assert.match(review,/Excel 原始菜名/)
  assert.match(review,/目前菜色/)
  assert.match(review,/確認變更/)
})

test('excluded lines retain persisted exclude and restore actions and confirmation',()=>{
  assert.match(review,/\/lines\/\$\{line\.id\}\/exclude/)
  assert.match(review,/\/lines\/\$\{line\.id\}\/restore/)
  assert.match(review,/只會從本次 Excel 匯入排除/)
  assert.match(review,/恢復此菜色/)
  assert.match(grid,/return'excluded'/)
  assert.match(grid,/menu-import-excluded-badge/)
  assert.match(css,/\.menu-import-cell\.excluded/)
  assert.match(css,/text-decoration:line-through/)
  assert.doesNotMatch(review,/setDetail\([^)]*resolution_status/)
})

test('duplicate conflicts have priority over review state and are summarized separately',()=>{
  const excludedIndex=grid.indexOf("return'excluded'")
  const duplicateIndex=grid.indexOf("return'duplicate'")
  const reviewIndex=grid.indexOf("return'needs-review'")
  assert.ok(excludedIndex>-1&&excludedIndex<duplicateIndex&&duplicateIndex<reviewIndex)
  assert.match(grid,/重複菜色/)
  assert.match(grid,/同一天同餐別已有相同菜色/)
  assert.match(css,/\.menu-import-cell\.duplicate\{background:#fff4e5/)
  assert.match(review,/detail\.summary\.duplicate_conflict_count/)
  assert.match(review,/detail\.summary\.excluded_count/)
  assert.match(review,/有效菜色/)
})

test('wide import matrix scrolls horizontally and responsive dialogs keep existing menu editor flow',()=>{
  assert.match(css,/\.menu-import-grid-wrap\{overflow:auto/)
  assert.match(css,/\.menu-import-grid\{width:100%;min-width:980px/)
  assert.match(css,/@media\(max-width:800px\)/)
  assert.match(menus,/onOpen\(item\)/)
})
