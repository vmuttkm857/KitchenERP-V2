import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import * as daily from '../src/features/requirements/dailyRequirements.ts'
import * as snapshots from '../src/features/snapshots/snapshotRequirements.ts'
import * as listQuery from '../src/utils/listQuery.ts'

function snapshot(id='snapshot-a') {
  return {id,revision:1,criteria:{},source_menus:[{menu_name:'歷史菜單',start_date:'2026-11-02',end_date:'2026-11-08'}],
    created_at:'2026-11-01',created_by_name:'測試',total_estimated_cost:'1',known_estimated_cost:'1',locked:false,
    purchase_ready:false,purchase_id:null,purchase_number:null,blocking_issues:[],anomaly_snapshot:[],
    items:['supplier-a','supplier-b'].map((supplier,index)=>({id:`item-${index}`,ingredient_id:`ingredient-${index}`,
      ingredient_code_snapshot:`I${index}`,ingredient_name_snapshot:'雞蛋',supplier_id:supplier,
      supplier_name_snapshot:supplier,supplier_code_snapshot:supplier,
      source_summary:[{requirement_date:'2026-11-02',menu_id:'menu',menu_name:'歷史菜單',quantity:'120',unit:'個'}]}))}
}

// Same lightweight hook/callback harness used by existing meal-editor tests.
function pageHarness() {
  const hooks=[],requests=[],downloads=[]
  let cursor=0,effects=[],tree,props={initialId:'snapshot-a'},downloadError=null,pendingDownload=null
  class ApiError extends Error {constructor(status,detail){super('API failed');this.status=status;this.detail=detail}}
  const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((value,index)=>Object.is(value,b[index]))
  const schedule=()=>queueMicrotask(render)
  const react={
    useState:initial=>{const index=cursor++;hooks[index]??={value:initial};return[hooks[index].value,next=>{hooks[index].value=typeof next==='function'?next(hooks[index].value):next;schedule()}]},
    useRef:initial=>{const index=cursor++;return hooks[index]??={current:initial}},
    useCallback:(fn,deps)=>{const index=cursor++;if(!hooks[index]||!equal(hooks[index].deps,deps))hooks[index]={deps,fn};return hooks[index].fn},
    useEffect:(callback,deps)=>{const index=cursor++,previous=hooks[index];if(!previous||!equal(previous.deps,deps))effects.push(()=>{previous?.cleanup?.();hooks[index]={deps,cleanup:callback()}})},
  }
  const exports={},jsx=(type,props)=>({type,props:props??{}})
  const source=readFileSync(new URL('../src/features/snapshots/SnapshotsPage.tsx',import.meta.url),'utf8')
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
    exports,URLSearchParams,window:{setTimeout},require:path=>{
      if(path==='react')return react
      if(path==='react/jsx-runtime')return {jsx,jsxs:jsx,Fragment:'Fragment'}
      if(path.endsWith('/api/client'))return {ApiError,apiRequest:async(path,init)=>{requests.push({path,init});return path.startsWith('/requirement-snapshots?')?{items:[],pagination:{total:0}}:snapshot(path.split('/').at(-1))},
        apiDownload:async path=>{downloads.push(path);if(pendingDownload)await pendingDownload;if(downloadError)throw new ApiError(422,{code:downloadError})}}
      if(path.endsWith('/listQuery'))return listQuery
      if(path.endsWith('/dailyRequirements'))return daily
      if(path==='./snapshotRequirements')return snapshots
      if(path.endsWith('/numbers'))return {formatMoney:value=>value,formatQuantity:value=>value}
      return {}
    },
  })
  function render(){cursor=0;effects=[];tree=exports.SnapshotsPage(props);const pending=effects;effects=[];pending.forEach(run=>run())}
  const nodes=value=>Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children)]:[]
  const text=value=>Array.isArray(value)?value.map(text).join(''):value&&typeof value==='object'?text(value.props?.children):typeof value==='string'?value:''
  render()
  return {
    requests,downloads,
    async settle(){await new Promise(done=>setTimeout(done,5))},
    button:label=>nodes(tree).find(node=>node.type==='button'&&text(node)===label),
    checkbox:()=>nodes(tree).find(node=>node.type==='input'&&node.props.type==='checkbox'),
    supplier:()=>nodes(tree).find(node=>node.type==='select'&&node.props.value?.startsWith('supplier-')),
    text:()=>text(tree),
    setSnapshot(id){props={initialId:id};render()},
    failWith(code){downloadError=code},
    waitDownload(promise){pendingDownload=promise},
  }
}

async function supplierView(){const ui=pageHarness();await ui.settle();ui.button('單一供應商').props.onClick();await ui.settle();return ui}

test('breakfast option defaults off and only changes this supplier download query',async()=>{
  const ui=await supplierView()
  assert.equal(ui.checkbox().props.checked,false)
  await ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  assert.equal(new URL(ui.downloads[0],'https://local').searchParams.get('breakfast_previous_day'),'false')
  ui.checkbox().props.onChange({target:{checked:true}});await ui.settle()
  await ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  const url=new URL(ui.downloads[1],'https://local')
  assert.equal(url.pathname,'/exports/requirement-snapshots/snapshot-a/suppliers/supplier-a/weekly-order.xlsx')
  assert.equal(url.searchParams.get('breakfast_previous_day'),'true')
  assert.ok(ui.requests.every(request=>!request.init)) // no save/settings API, and no browser storage provided
})

test('changing supplier or snapshot revision clears the breakfast option',async()=>{
  const ui=await supplierView()
  ui.checkbox().props.onChange({target:{checked:true}});await ui.settle()
  ui.supplier().props.onChange({target:{value:'supplier-b'}});await ui.settle()
  assert.equal(ui.checkbox().props.checked,false)
  ui.checkbox().props.onChange({target:{checked:true}});await ui.settle()
  ui.setSnapshot('snapshot-revision-b');await ui.settle()
  ui.button('單一供應商').props.onClick();await ui.settle()
  assert.equal(ui.checkbox().props.checked,false)
  await ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  assert.match(ui.downloads.at(-1),/snapshot-revision-b\/suppliers\/supplier-a\//)
})

test('missing historical meal displays a clear error and ordinary retry remains available',async()=>{
  const ui=await supplierView()
  ui.failWith('SUPPLIER_ORDER_MEAL_UNAVAILABLE')
  ui.checkbox().props.onChange({target:{checked:true}});await ui.settle()
  await ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  assert.match(ui.text(),/部分歷史明細缺少可追溯餐別.*請取消勾選後下載一般叫貨單/)
  assert.equal(ui.checkbox().props.checked,true)
  assert.equal(ui.button('下載此供應商每週叫貨 Excel').props.disabled,false)
  ui.failWith(null);ui.checkbox().props.onChange({target:{checked:false}});await ui.settle()
  await ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  assert.match(ui.downloads.at(-1),/breakfast_previous_day=false$/)
})

test('breakfast checkbox and download are disabled while producing the workbook',async()=>{
  const ui=await supplierView()
  let release;ui.waitDownload(new Promise(resolve=>{release=resolve}))
  ui.button('下載此供應商每週叫貨 Excel').props.onClick();await ui.settle()
  assert.equal(ui.checkbox().props.disabled,true)
  assert.equal(ui.button('產生中…').props.disabled,true)
  release();await ui.settle()
  assert.equal(ui.checkbox().props.disabled,false)
})
