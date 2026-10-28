import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import {RequestSequence} from '../src/utils/listQuery.ts'
import * as daily from '../src/features/requirements/dailyRequirements.ts'
import * as numbers from '../src/utils/numbers.ts'

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}
const menu=id=>({id,name:id,start_date:'2026-11-02',end_date:'2026-11-08',is_active:true})
function result(id){return {rows:[],daily_rows:[{requirement_date:'2026-11-02',menu_id:id,menu_name:id,supplier_id:'supplier',supplier_name:'供應商',ingredient_id:'ingredient',ingredient_code:'I1',ingredient_name:'青菜',quantity:'3.15',unit:'kg'}],known_estimated_cost:'0',total_estimated_cost:'0',anomalies:[],anomaly_summary:{total:0,errors:0,warnings:0}}}
const context=id=>({id,revision:1,lock_version:1,source_fingerprint:'a'.repeat(64),criteria:{menu_ids:['A'],start_date:'2026-11-02',end_date:'2026-11-08'},source_menus:[{menu_id:'A',menu_name:'A',start_date:'2026-11-02',end_date:'2026-11-08',is_active:true}]})
const nodes=value=>Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children)]:[]
const text=value=>Array.isArray(value)?value.map(text).join(''):value&&typeof value==='object'?text(value.props?.children):typeof value==='string'?value:''

// Executes the real RequirementsPage callbacks/hooks. This is a lightweight
// hook harness, not a browser, React DOM renderer, or a duplicate controller.
function harness(adjustmentContext){
  let hooks=[],cursor=0,effects=[],tree,scheduled=false,closed=false
  let props={adjustmentContext,onOpenSnapshot:id=>opened.push(id)}
  const calls=[],downloads=[],copies=[],opened=[],timers=[],lateUpdates=[]
  let exports={}
  const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]))
  function render(){if(closed)return;scheduled=false;cursor=0;effects=[];tree=exports.RequirementsPage(props);const pending=effects;effects=[];pending.forEach(run=>run())}
  function schedule(){if(!scheduled&&!closed){scheduled=true;queueMicrotask(render)}}
  const react={
    useState(initial){const index=cursor++;hooks[index]??={value:typeof initial==='function'?initial():initial};return [hooks[index].value,next=>{if(closed){lateUpdates.push(index);return}const value=typeof next==='function'?next(hooks[index].value):next;if(!Object.is(value,hooks[index].value)){hooks[index].value=value;schedule()}}]},
    useRef(initial){const index=cursor++;return hooks[index]??={current:initial}},
    useEffect(effect,deps){const index=cursor++,old=hooks[index];if(!old||!equal(old.deps,deps))effects.push(()=>{old?.cleanup?.();hooks[index]={deps,cleanup:effect()}})},
  }
  react.useLayoutEffect=react.useEffect
  const Candidate=()=>{},Filters=()=>{}
  class ApiError extends Error{constructor(status,detail){super('API failed');this.status=status;this.detail=detail}}
  const api={ApiError,
    apiRequest(path,init){const request={path,init,body:JSON.parse(init.body),...deferred()};calls.push(request);return request.promise},
    async apiDownload(path,init,canDownload){const request={path,init,body:JSON.parse(init.body),...deferred()};calls.push(request);await request.promise;if(!canDownload||canDownload())downloads.push(request.body)},
  }
  const source=readFileSync(new URL('../src/features/requirements/RequirementsPage.tsx',import.meta.url),'utf8')
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText
  vm.runInNewContext(compiled,{exports,console,URLSearchParams,window:{setTimeout:fn=>{timers.push(fn)}},require:path=>{
    if(path==='react')return react
    if(path==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'}
    if(path.endsWith('/api/client'))return api
    if(path.endsWith('/listQuery'))return {RequestSequence}
    if(path==='./dailyRequirements')return daily
    if(path.endsWith('/numbers'))return numbers
    if(path.endsWith('/clipboard'))return {writeClipboard:async value=>{copies.push(value)}}
    if(path.endsWith('/anomalies'))return {groupAnomalies:()=>[]}
    if(path.endsWith('/MenuCandidateFilters'))return {MenuCandidateOption:Candidate,MenuCandidateFilters:Filters,menuMonthRange:()=>({})}
    if(path.endsWith('/useMenuCandidates'))return {useMenuCandidates:()=>({items:[menu('A'),menu('B')],total:2,page:1,pageSize:20,search:'',setPage(){},setSearch(){},loading:false,error:''})}
    return {}
  }})
  render()
  const findButton=label=>nodes(tree).find(node=>node.type==='button'&&text(node)===label)
  const ui={calls,downloads,copies,opened,timers,lateUpdates,ApiError,
    async flush(){for(let i=0;i<12;i++)await Promise.resolve()},
    toggle(id){nodes(tree).find(node=>node.type===Candidate&&node.props.menu.id===id).props.onToggle()},
    calculate(){return nodes(tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}})},
    button:findButton,
    click(label){const button=findButton(label);assert.ok(button,`Missing button ${label}`);return button.props.onClick()},
    customDates(){const label=nodes(tree).find(node=>node.type==='label'&&text(node)==='自訂日期範圍');nodes(label).find(node=>node.type==='input').props.onChange()},
    date(index,value){nodes(tree).filter(node=>node.type==='input'&&node.props.type==='date')[index].props.onChange({target:{value}})},
    basis(value){nodes(tree).find(node=>node.type==='input'&&node.props.name==='quantity-basis'&&node.props.value===value).props.onChange()},
    setContext(value){props={...props,adjustmentContext:value};render()},
    filters(){return nodes(tree).find(node=>node.type===Filters).props},
    resultMenus(){return nodes(tree).find(node=>node.type?.name==='DailyRequirementTable')?.props.rows.map(row=>row.menu_id)??[]},
    loading(){return Boolean(findButton('計算中…'))},
    texts(){return text(tree)},
    requests(path){return calls.filter(call=>call.path===path)},
    close(){closed=true;hooks.forEach(hook=>hook?.cleanup?.())},
  }
  return ui
}

async function calculated(ui,id='A'){
  const pending=ui.calculate();await ui.flush()
  ui.requests('/requirements/calculate').at(-1).resolve(result(id))
  await pending;await ui.flush()
}

test('A: changing menus invalidates a pending calculation without restoring old results',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const pending=ui.calculate();await ui.flush();ui.toggle('A');ui.toggle('B');await ui.flush()
  ui.requests('/requirements/calculate')[0].resolve(result('A'));await pending;await ui.flush()
  assert.deepEqual(ui.resultMenus(),[]);assert.equal(ui.button('儲存為固定需求快照'),undefined);assert.equal(ui.loading(),false)
})

for(const index of [0,1])test(`B: changing ${index?'end':'start'} date rejects the old result`,async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();ui.customDates();await ui.flush()
  const pending=ui.calculate();await ui.flush();ui.date(index,index?'2026-11-07':'2026-11-03');await ui.flush()
  ui.requests('/requirements/calculate')[0].resolve(result('OLD'));await pending;await ui.flush()
  assert.deepEqual(ui.resultMenus(),[]);assert.equal(ui.button('下載 Excel'),undefined)
})

test('C: B completes before A and remains the visible result',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const a=ui.calculate();await ui.flush();ui.toggle('A');ui.toggle('B');await ui.flush()
  const b=ui.calculate();await ui.flush();const [old,current]=ui.requests('/requirements/calculate')
  current.resolve(result('B'));await b;await ui.flush();assert.deepEqual(ui.resultMenus(),['B'])
  old.resolve(result('A'));await a;await ui.flush();assert.deepEqual(ui.resultMenus(),['B'])
})

test('D: a late A failure does not end B loading or display an obsolete error',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const a=ui.calculate();await ui.flush();ui.toggle('B');await ui.flush();const b=ui.calculate();await ui.flush()
  ui.requests('/requirements/calculate')[0].reject(Error('old error'));await a;await ui.flush()
  assert.equal(ui.loading(),true);assert.doesNotMatch(ui.texts(),/需求量計算失敗/)
  ui.requests('/requirements/calculate')[1].resolve(result('B'));await b;await ui.flush()
  assert.deepEqual(ui.resultMenus(),['B']);assert.doesNotMatch(ui.texts(),/需求量計算失敗/)
})

test('D: a late A failure cannot alter an already successful B',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const a=ui.calculate();await ui.flush();ui.toggle('B');await ui.flush();const b=ui.calculate();await ui.flush()
  ui.requests('/requirements/calculate')[1].resolve(result('B'));await b;await ui.flush()
  ui.requests('/requirements/calculate')[0].reject(Error('old error'));await a;await ui.flush()
  assert.deepEqual(ui.resultMenus(),['B']);assert.doesNotMatch(ui.texts(),/需求量計算失敗/);assert.equal(ui.loading(),false)
})

test('E: rapid menu/date/basis changes accept only the final request',async t=>{
  const ui=harness(context('sheet'));t.after(()=>ui.close());await ui.flush()
  const pending=[]
  for(let i=0;i<4;i++){pending.push(ui.calculate());await ui.flush();ui.date(0,`2026-11-0${i+3}`);ui.basis(i%2?'actual':'theoretical');await ui.flush()}
  pending.push(ui.calculate());await ui.flush()
  const requests=ui.requests('/requirements/calculate');requests.at(-1).resolve(result('FINAL'));await pending.at(-1);await ui.flush()
  for(let i=3;i>=0;i--){requests[i].resolve(result('OLD'));await pending[i];await ui.flush()}
  assert.deepEqual(ui.resultMenus(),['FINAL'])
})

test('F: retained old save/download/copy/navigation handlers cannot act after invalidation',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  const handlers=['儲存為固定需求快照','下載 Excel','複製目前表格','前往正式採購'].map(label=>ui.button(label).props.onClick)
  const count=ui.calls.length;ui.toggle('B')
  handlers.forEach(handler=>handler());await ui.flush()
  assert.equal(ui.calls.length,count);assert.deepEqual(ui.copies,[]);assert.deepEqual(ui.opened,[])
})

test('F: snapshot response for A does not announce or navigate as B',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  ui.click('儲存為固定需求快照');await ui.flush();const save=ui.requests('/requirement-snapshots')[0]
  ui.toggle('B');await ui.flush();await calculated(ui,'B');save.resolve({id:'snapshot-A'});await ui.flush()
  assert.doesNotMatch(ui.texts(),/固定需求快照已建立/);ui.click('前往正式採購');assert.deepEqual(ui.opened,[])
})

test('F: pending export is not downloaded after conditions change',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  ui.click('下載 Excel');await ui.flush();const download=ui.calls.at(-1)
  ui.toggle('B');await ui.flush();download.resolve();await ui.flush()
  assert.deepEqual(ui.downloads,[]);assert.equal(ui.loading(),false)
})

test('normal result can be copied exported saved and opened with its captured criteria',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  const criteria=ui.requests('/requirements/calculate')[0].body
  ui.click('下載 Excel');await ui.flush();assert.deepEqual(ui.calls.at(-1).body,criteria);ui.calls.at(-1).resolve();await ui.flush()
  assert.deepEqual(ui.downloads,[criteria]);ui.click('複製目前表格');await ui.flush();assert.equal(ui.copies.length,1)
  ui.click('儲存為固定需求快照');await ui.flush();const save=ui.requests('/requirement-snapshots')[0];assert.deepEqual(save.body,{criteria})
  save.resolve({id:'snapshot-A'});await ui.flush();ui.click('前往正式採購');assert.deepEqual(ui.opened,['snapshot-A'])
})

test('context replacement and unmount invalidate pending responses',async t=>{
  const ui=harness(context('sheet-A'));t.after(()=>ui.close());await ui.flush();const a=ui.calculate();await ui.flush()
  ui.setContext(context('sheet-B'));await ui.flush();ui.requests('/requirements/calculate')[0].resolve(result('OLD'));await a;await ui.flush()
  assert.deepEqual(ui.resultMenus(),[])
  const b=ui.calculate();await ui.flush();ui.close();ui.requests('/requirements/calculate')[1].resolve(result('UNMOUNTED'));await b
  assert.deepEqual(ui.lateUpdates,[])
})

test('candidate filters do not invalidate an otherwise current calculation',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const pending=ui.calculate();await ui.flush();ui.filters().onMonth('2026-12');ui.filters().onCategoryId('category');await ui.flush()
  ui.requests('/requirements/calculate')[0].resolve(result('A'));await pending;await ui.flush();assert.deepEqual(ui.resultMenus(),['A'])
})

test('a current calculation error is shown and loading ends',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();const pending=ui.calculate();await ui.flush()
  ui.requests('/requirements/calculate')[0].reject(Error('network'));await pending;await ui.flush()
  assert.match(ui.texts(),/需求量計算失敗/);assert.equal(ui.loading(),false);assert.deepEqual(ui.resultMenus(),[])
})

test('starting another calculation immediately revokes the previous result handlers',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  const oldSave=ui.button('儲存為固定需求快照').props.onClick
  const pending=ui.calculate();oldSave();await ui.flush()
  assert.equal(ui.requests('/requirement-snapshots').length,0)
  ui.requests('/requirements/calculate').at(-1).resolve(result('LATEST'));await pending;await ui.flush();assert.deepEqual(ui.resultMenus(),['LATEST'])
})

test('old handlers remain invalid even after a different valid result arrives',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  const handlers=['儲存為固定需求快照','下載 Excel','複製目前表格'].map(label=>ui.button(label).props.onClick)
  ui.toggle('B');await ui.flush();await calculated(ui,'B');const count=ui.calls.length
  handlers.forEach(handler=>handler());await ui.flush();assert.equal(ui.calls.length,count);assert.deepEqual(ui.copies,[])
})

test('an obsolete snapshot failure/finally cannot end a newer snapshot save',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  ui.click('儲存為固定需求快照');await ui.flush();const old=ui.requests('/requirement-snapshots')[0]
  ui.toggle('B');await ui.flush();await calculated(ui,'B');ui.click('儲存為固定需求快照');await ui.flush()
  old.reject(Error('obsolete save'));await ui.flush()
  assert.ok(ui.button('儲存中…'));assert.doesNotMatch(ui.texts(),/固定快照建立失敗/)
  ui.requests('/requirement-snapshots')[1].resolve({id:'snapshot-B'});await ui.flush();ui.click('前往正式採購');assert.deepEqual(ui.opened,['snapshot-B'])
})

test('an obsolete download failure/finally cannot end newer calculation loading',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  ui.click('下載 Excel');await ui.flush();const old=ui.calls.at(-1)
  ui.toggle('B');await ui.flush();const pending=ui.calculate();await ui.flush();old.reject(Error('obsolete download'));await ui.flush()
  assert.equal(ui.loading(),true);assert.doesNotMatch(ui.texts(),/Excel 下載失敗/)
  ui.requests('/requirements/calculate').at(-1).resolve(result('B'));await pending;await ui.flush();assert.deepEqual(ui.resultMenus(),['B'])
})

test('snapshot and download duplicate clicks are guarded before React rerenders',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush();await calculated(ui)
  const save=ui.button('儲存為固定需求快照').props.onClick,download=ui.button('下載 Excel').props.onClick
  save();save();download();download();await ui.flush()
  assert.equal(ui.requests('/requirement-snapshots').length,1);assert.equal(ui.calls.filter(call=>call.path.startsWith('/exports/')).length,1)
  ui.requests('/requirement-snapshots')[0].resolve({id:'saved'});ui.calls.find(call=>call.path.startsWith('/exports/')).resolve();await ui.flush()
})

test('actual quantity basis retains the selected source and date contract',async t=>{
  const ui=harness(context('confirmed-sheet'));t.after(()=>ui.close());await ui.flush();await calculated(ui)
  const criteria=ui.requests('/requirements/calculate')[0].body
  assert.deepEqual(criteria,{menu_ids:['A'],start_date:'2026-11-02',end_date:'2026-11-08',ordering_adjustment_sheet_ids:['confirmed-sheet']})
  ui.click('儲存為固定需求快照');await ui.flush();assert.deepEqual(ui.requests('/requirement-snapshots')[0].body,{criteria})
  ui.requests('/requirement-snapshots')[0].resolve({id:'saved'});await ui.flush()
})

test('range mode changes revoke pending results but weight display changes preserve them',async t=>{
  const ui=harness();t.after(()=>ui.close());await ui.flush();ui.toggle('A');await ui.flush()
  const old=ui.calculate();await ui.flush();ui.customDates();await ui.flush();ui.requests('/requirements/calculate')[0].resolve(result('OLD'));await old;await ui.flush()
  assert.deepEqual(ui.resultMenus(),[]);await calculated(ui);ui.click('重量換算 kg');await ui.flush();assert.deepEqual(ui.resultMenus(),['A'])
})

function downloadClient(){
  const body=deferred(),clicks=[],calls=[];let exports={}
  const source=readFileSync(new URL('../src/api/client.ts',import.meta.url),'utf8').replace('import.meta.env.VITE_API_BASE_URL','undefined')
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
    exports,Headers,console,fetch:async(path,init)=>{calls.push({path,init});return {status:200,ok:true,headers:new Headers(),blob:()=>body.promise}},
    require:()=>({beginApiObservation:()=>null}),URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
    document:{createElement:()=>({style:{},click:()=>clicks.push('download'),remove(){}}),body:{appendChild(){}}},window:{setTimeout:fn=>fn()},
  })
  return {api:exports,body,clicks,calls}
}

test('real apiDownload checks optional validity after reading the response body',async()=>{
  const runtime=downloadClient();let current=true
  const pending=runtime.api.apiDownload('/exports/requirements/xlsx',{method:'POST',body:'{}'},()=>current)
  await Promise.resolve();current=false;runtime.body.resolve({});await pending
  assert.deepEqual(runtime.clicks,[]);assert.equal(runtime.calls.length,1)
})

test('real apiDownload preserves downloads without a guard or with a current guard',async()=>{
  for(const guard of [undefined,()=>true]){const runtime=downloadClient();const pending=runtime.api.apiDownload('/exports/requirements/xlsx',undefined,guard);runtime.body.resolve({});await pending;assert.deepEqual(runtime.clicks,['download']);assert.equal(runtime.calls.length,1)}
})
