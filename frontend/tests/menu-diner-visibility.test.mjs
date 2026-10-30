import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import {mealGridRows} from '../src/features/menus/menuGridRows.ts'
import {canInsertMenuDish} from '../src/features/menus/menuDrag.ts'
import {mealSectionTone} from '../src/features/menus/mealSectionTone.ts'
const jsx=(type,props)=>({type,props})
const nodes=x=>Array.isArray(x)?x.flatMap(nodes):x&&typeof x==='object'?[x,...nodes(x.props?.children)]:[]
const text=x=>Array.isArray(x)?x.map(text).join(''):x&&typeof x==='object'?text(x.props?.children):typeof x==='string'||typeof x==='number'?String(x):''
function load(name,react,modules){
 const exports={}
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL(`../src/features/menus/${name}.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,require:p=>p==='react'?react:p==='react/jsx-runtime'?{jsx,jsxs:jsx}:modules[p]??{}})
 return exports[name]
}
// Runs real component callbacks with controlled hooks, not React DOM or browser E2E.
const Grid=load('MenuWeekGrid',{useState:x=>[x,()=>{}],useRef:x=>({current:x}),useEffect(){}},{'./menuGridRows':{mealGridRows},'./menuDrag':{canInsertMenuDish},'./mealSectionTone':{mealSectionTone}})
const meal={id:'meal',menu_id:'menu',name:'午餐',sort_order:1,is_active:true}
const dishes=[{id:'first',dish_id:'a',dish_name:'香菇燴雞肉長菜名',diner_count:12,sort_order:1,menu_meal_type_column_id:null,notes:null},{id:'second',dish_id:'b',dish_name:'炒青菜',diner_count:0,sort_order:2,menu_meal_type_column_id:null,notes:null}]
const aggregate={menu:{id:'menu',name:'測試菜單',start_date:'2026-11-09',end_date:'2026-11-10'},dates:['2026-11-09','2026-11-10'],meal_types:[meal],meal_type_columns:[],slots:['2026-11-09','2026-11-10'].map(menu_date=>({menu_date,menu_meal_type_id:'meal',notes:null,dishes:structuredClone(dishes)}))}
function harness(){
 let hooks=[],cursor=0,effects=[],scheduled=false,tree,props={menu:aggregate.menu,onClose(){}}
 const calls=[],candidates={items:[],loading:false},Dialog=()=>{}
 const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>Object.is(x,b[i]))
 const schedule=()=>{if(!scheduled){scheduled=true;queueMicrotask(render)}}
 const react={
 useState(initial){const i=cursor++;hooks[i]??={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{const value=typeof next==='function'?next(hooks[i].value):next;if(!Object.is(value,hooks[i].value)){hooks[i].value=value;schedule()}}]},
 useMemo(fn,deps){const i=cursor++;if(!hooks[i]||!equal(hooks[i].deps,deps))hooks[i]={deps,value:fn()};return hooks[i].value},
 useCallback(fn,deps){return react.useMemo(()=>fn,deps)},
 useEffect(fn,deps){const i=cursor++;if(!hooks[i]||!equal(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn)}}
 }
 const Editor=load('MenuEditor',react,{'../../api/client':{apiRequest:async(path,init)=>{calls.push({path,init});return structuredClone({...aggregate,menu:props.menu})}},'../../app/NavigationBlocker':{useEditorDirty(){}},'./MenuWeekGrid':{MenuWeekGrid:Grid},'./MenuMealEditorDialog':{MenuMealEditorDialog:Dialog},'./useMenuCandidates':{useMenuCandidates:()=>candidates}})
 function render(){scheduled=false;cursor=0;effects=[];tree=Editor(props);const pending=effects;effects=[];pending.forEach(fn=>fn())}
 render()
 return {calls,async flush(){for(let i=0;i<15;i++)await Promise.resolve()},button(label){return nodes(tree).find(n=>n.type==='button'&&text(n)===label)},grid(){return nodes(tree).find(n=>n.type===Grid)},cards(){return Grid(this.grid().props)},dialog(){return nodes(tree).find(n=>n.type===Dialog)},changeMenu(){props={...props,menu:{...props.menu,id:'other'}};render()}}
}
test('editor toggles all counts without changing names, ordering, data or API calls; edit entry remains available',async()=>{
 const ui=harness();await ui.flush();const before=JSON.stringify(aggregate),count=ui.calls.length
 assert.equal(ui.grid().props.showDinerCounts,false);assert.equal(ui.button('顯示人數').props['aria-pressed'],false)
 const names=()=>nodes(ui.cards()).filter(n=>n.type==='strong').map(text)
 const expected=names();assert.equal(expected.length,4)
 assert.equal(nodes(ui.cards()).filter(n=>n.type==='span'&&/ 人$/.test(text(n))).length,0)
 ui.button('顯示人數').props.onClick();await ui.flush()
 assert.equal(ui.button('隱藏人數').props['aria-pressed'],true)
 assert.deepEqual(nodes(ui.cards()).filter(n=>n.type==='span'&&/ 人$/.test(text(n))).map(text),['12 人','12 人','0 人','0 人'])
 assert.deepEqual(names(),expected)
 ui.button('隱藏人數').props.onClick();await ui.flush()
 assert.equal(ui.grid().props.showDinerCounts,false);assert.deepEqual(names(),expected)
 assert.equal(ui.calls.length,count);assert.equal(JSON.stringify(aggregate),before)
 assert.ok(ui.calls.every(c=>!c.init?.method||c.init.method==='GET'))
 nodes(ui.cards()).find(n=>n.type==='button'&&n.props['aria-label']==='編輯 2026-11-09 午餐').props.onClick()
 await ui.flush();assert.ok(ui.dialog())
})
test('a different menu resets counts to hidden',async()=>{
 const ui=harness();await ui.flush();ui.button('顯示人數').props.onClick();await ui.flush();assert.equal(ui.grid().props.showDinerCounts,true)
 ui.changeMenu();await ui.flush();assert.equal(ui.grid().props.showDinerCounts,false)
})
test('other grid callers retain their original visible default',()=>{
 const before=JSON.stringify(aggregate)
 const tree=Grid({dates:aggregate.dates,meals:[meal],columns:[],selectedKey:null,slotFor:date=>aggregate.slots.find(s=>s.menu_date===date),onSelect(){},onEditColumns(){},onMoveDish:async()=>{},movingDish:false})
 assert.equal(nodes(tree).filter(n=>n.type==='span'&&/ 人$/.test(text(n))).length,4)
 assert.equal(JSON.stringify(aggregate),before)
})
