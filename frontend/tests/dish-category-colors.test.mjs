import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as display from '../src/features/categories/categoryDisplay.js'
import { MealEditorController } from '../src/features/menus/mealEditorController.ts'

const jsx = (type, props) => ({ type, props })
const nodes = x => Array.isArray(x) ? x.flatMap(nodes) : x && typeof x === 'object' ? [x, ...nodes(x.props?.children)] : []
const text = x => Array.isArray(x) ? x.map(text).join('') : x && typeof x === 'object' ? text(x.props?.children) : typeof x === 'string' || typeof x === 'number' ? String(x) : ''
function load(file, react = {}, modules = {}, extra = '') {
  const exports = {}
  const output = ts.transpileModule(readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText
  vm.runInNewContext(output + extra, { exports, console, window: { addEventListener() {}, removeEventListener() {} }, require: path => {
    if (path === 'react') return react
    if (path === 'react/jsx-runtime') return { jsx, jsxs: jsx }
    if (path.endsWith('categoryDisplay.js')) return display
    return modules[path] ?? {}
  } })
  return exports
}

// Controlled hooks and real component callbacks, not React DOM/browser E2E.
function hooks(factory, initialProps) {
  let state = [], cursor = 0, effects = [], pending = false, tree, props = initialProps
  const equal = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]))
  const schedule = () => { if (!pending) { pending = true; queueMicrotask(render) } }
  const react = {
    useState(initial) { const i = cursor++; state[i] ??= { value: typeof initial === 'function' ? initial() : initial }; return [state[i].value, next => { state[i].value = typeof next === 'function' ? next(state[i].value) : next; schedule() }] },
    useRef(value) { const i = cursor++; state[i] ??= { current: value }; return state[i] },
    useMemo(fn, deps) { const i = cursor++; if (!state[i] || !equal(state[i].deps, deps)) state[i] = { value: fn(), deps }; return state[i].value },
    useCallback(fn, deps) { return react.useMemo(() => fn, deps) },
    useEffect(fn, deps) { const i = cursor++; if (!state[i] || !equal(state[i].deps, deps)) { const previous = state[i]; state[i] = { deps }; effects.push(() => { previous?.cleanup?.(); state[i].cleanup = fn() }) } },
  }
  const component = factory(react)
  function render() { cursor = 0; pending = false; effects = []; tree = component(props); const active = effects; effects = []; active.forEach(effect => effect()) }
  render()
  return { get tree() { return tree }, async flush() { for (let i = 0; i < 25; i++) await Promise.resolve() }, update(next) { props = next; render() } }
}

const category = { id: 'cat-id', name: '原分類', is_active: true, sort_order: 0, background_color: '#BBDEFB' }
const Picker = load('features/categories/CategoryColorPicker.tsx').CategoryColorPicker
const Search = load('features/menus/DishSearchPicker.tsx').DishSearchPicker
const Panel = load('features/menus/MenuEditorPanel.tsx', { useRef: value => ({ current: value }) }, { './DishSearchPicker': { DishSearchPicker: Search } }).MenuEditorPanel
const dish = { id: 'dish-id', name: '完全相同的顯示名稱', code: 'D1', category_id: category.id, category_name: '不可靠名稱', recipe_ingredient_count: 2, is_active: true }
const slotDish = { dish_id: dish.id, dish_name: dish.name, dish_code: dish.code, dish_category_name: '另一名稱', menu_meal_type_column_id: null, diner_count: 20, notes: null, sort_order: 1 }
function panelProps(extra = {}) {
  return { date: '2026-11-09', meal: { id: 'meal', name: '午餐', is_active: true }, columns: [], slot: { dishes: [slotDish] },
    categories: [category], dishCategoryIds: { [dish.id]: category.id }, results: [dish], search: '菜', categoryId: '', searchTotal: 1, searchPage: 1,
    searchInputRef: { current: null }, onAdd() {}, onClose() {}, onMove() {}, onRemove() {}, onSave() {}, ...extra }
}
const article = tree => nodes(tree).find(node => node.type === 'article')
const result = tree => nodes(tree).find(node => node.props?.className === 'dish-result')

test('both entire row containers use the same authoritative category ID, not names; other callers opt out', () => {
  const props = panelProps({ showCategoryColors: true }), before = JSON.stringify(props)
  const left = Panel(props), searchNode = nodes(left).find(node => node.type === Search), right = Search(searchNode.props)
  assert.deepEqual(article(left).props.style, result(right).props.style)
  assert.equal(article(left).props.style['--dish-category-background'], '#BBDEFB')
  assert.equal(JSON.stringify(props), before)
  assert.equal(article(Panel(panelProps())).props.style, undefined)
  assert.equal(result(Search({ ...searchNode.props, showCategoryColors: undefined })).props.style, undefined)
  const mismatched = Panel(panelProps({ showCategoryColors: true, dishCategoryIds: { [dish.id]: 'missing' } }))
  assert.equal(article(mismatched).props.style, undefined)
})

test('inactive, renamed and reordered categories retain color; absent/null/invalid colors stay neutral', () => {
  for (const changed of [{ is_active: false }, { name: '已改名' }, { sort_order: 999 }]) {
    const tree = Panel(panelProps({ showCategoryColors: true, categories: [{ ...category, ...changed }] }))
    assert.equal(article(tree).props.style['--dish-category-background'], '#BBDEFB')
  }
  for (const color of [null, undefined, 'red', '#123', 'url(secret)']) {
    assert.equal(display.categoryRowStyle(category.id, new Map([[category.id, { background_color: color }]]), true), undefined)
  }
})

test('palette has ten readable choices; clear/selection callbacks never submit a form', () => {
  assert.equal(display.DISH_BACKGROUND_COLORS.length, 10)
  const calls = [], tree = Picker({ value: '#BBDEFB', disabled: false, onChange: value => calls.push(value) })
  const buttons = nodes(tree).filter(node => node.type === 'button')
  assert.equal(buttons.length, 11)
  assert.equal(buttons.filter(node => node.props['aria-pressed']).length, 1)
  assert.ok(buttons.every(node => node.props.type === 'button'))
  buttons.find(node => text(node) === '無顏色').props.onClick()
  buttons.find(node => text(node) === '淺粉').props.onClick()
  assert.deepEqual(calls, [null, '#FCE4EC'])
  assert.equal(Picker({ value: null, disabled: true, onChange() {} }).props.disabled, true)
  for (const color of display.DISH_BACKGROUND_COLORS) {
    const style = display.categoryRowStyle('id', new Map([['id', { background_color: color.value }]]), true)
    assert.equal(style['--dish-category-text'], '#000000')
  }
  assert.equal(display.categoryRowStyle('id', new Map([['id', { background_color: '#000000' }]]), true)['--dish-category-text'], '#FFFFFF')
})

test('more than 100 categories load all pages, including inactive records; incomplete/duplicate pages fail', async () => {
  const categories = Array.from({ length: 205 }, (_, i) => ({ ...category, id: String(i), is_active: i !== 204 }))
  const calls = []
  const loaded = await display.loadDishCategories(async path => {
    calls.push(path); const page = Number(new URLSearchParams(path.split('?')[1]).get('page') ?? 1)
    return { items: categories.slice((page - 1) * 100, page * 100), pagination: { total: 205 } }
  })
  assert.deepEqual(loaded, categories)
  assert.equal(calls.length, 3)
  assert.equal(display.categoryRowStyle('204', new Map(loaded.map(item => [item.id, item])), true)['--dish-category-background'], '#BBDEFB')
  await assert.rejects(display.loadDishCategories(async path => ({ items: path.includes('page=2') ? [] : categories.slice(0,100), pagination: { total:205 } })))
  await assert.rejects(display.loadDishCategories(async () => ({ items: [category, category], pagination: { total:2 } })))
  assert.deepEqual(await display.loadDishCategories(async () => ({ items:categories }), () => false), [])
})

test('controller keeps display map out of dirty state and save payload; add/move/remove and reload colors work', async () => {
  let color = '#BBDEFB'
  const calls = [], source = { menu_day_id:'day',menu_date:'2026-11-09',menu_meal_type_id:'meal',notes:null,dishes:[slotDish],slot_fingerprint:'a'.repeat(64),dish_category_ids:{[dish.id]:category.id} }
  const aggregate = { menu:{id:'menu'},meal_types:[{id:'meal',is_active:true}],meal_type_columns:[],slots:[],dish_category_ids:source.dish_category_ids }
  const controller = new MealEditorController('menu','2026-11-09','meal',async(path,init) => {
    calls.push({path,init})
    if (init) return aggregate
    if (path.includes('meal-slots')) return structuredClone(source)
    if (path.endsWith('editor')) return aggregate
    return { items:[{...category,background_color:color}],pagination:{total:1} }
  })
  await controller.load()
  assert.deepEqual(controller.getSnapshot().dishCategoryIds, source.dish_category_ids)
  assert.equal('dish_category_ids' in controller.getSnapshot().slot, false)
  assert.equal(controller.getSnapshot().dirty, false)
  color = '#FCE4EC'; await controller.load()
  assert.equal(controller.getSnapshot().categories[0].background_color, color)
  assert.equal(controller.getSnapshot().dirty, false)
  controller.add({...dish,id:'new'})
  assert.equal(controller.getSnapshot().dishCategoryIds.new,category.id)
  controller.move(1,-1); controller.remove(1)
  assert.deepEqual(controller.getSnapshot().slot.dishes.map(item=>item.dish_id),['new'])
  await controller.save()
  const payload=JSON.parse(calls.find(call=>call.init).init.body)
  assert.equal(payload.expected_slot_fingerprint,'a'.repeat(64))
  assert.equal('dish_category_ids' in payload,false)
  assert.equal('background_color' in payload.dishes[0],false)
  assert.equal('category_id' in payload.dishes[0],false)
  assert.equal(payload.dishes[0].diner_count,1)
  assert.equal(controller.getSnapshot().dirty,false)
})

function management(request) {
  const Empty=()=>{},Color=()=>{},Feedback=()=>{}
  const ui=hooks(react=>load('features/categories/CategoriesPage.tsx',react,{
    '../../api/client':{ApiError:class ApiError extends Error{},apiRequest:request},
    './CategoryColorPicker':{CategoryColorPicker:Color},
    '../../components/ui/Page':{Feedback,EmptyState:Empty},
  }).CategoriesPage,{})
  return {ui,Empty,Color,
    tab(label){const tabs=nodes(ui.tree).find(node=>node.type?.name==='CategoryTypeTabs');return nodes(tabs.type(tabs.props)).find(node=>node.props?.role==='tab'&&text(node)===label)},
    button(label){return nodes(ui.tree).find(node=>node.type==='button'&&text(node)===label)},
    row(name){return nodes(ui.tree).find(node=>node.type==='tr'&&nodes(node).some(child=>child.type==='strong'&&text(child)===name))},
    dialog(){return nodes(ui.tree).find(node=>node.type?.name==='CategoryDialog')},
  }
}

test('simple create then edit persists color, full name-cell preview, inactive/reorder and clear; failures retain draft', async () => {
  const calls=[],records={dish:[{...category}],ingredient:[{...category,id:'ingredient'}]}
  let fail=false
  const page=management(async(path,init)=>{
    calls.push({path,init})
    const parts=path.split('?')[0].split('/'),kind=parts[2]
    if(!init)return {items:structuredClone(records[kind]).sort((a,b)=>a.sort_order-b.sort_order),pagination:{total:records[kind].length}}
    if(fail)throw Error('offline')
    const body=init.body?JSON.parse(init.body):{}
    if(init.method==='POST'&&parts.length===3){const created={...category,...body,id:'new',background_color:null};records[kind].push(created);return structuredClone(created)}
    const record=records[kind].find(item=>item.id===parts[3])
    if(init.method==='PATCH')Object.assign(record,body)
    if(parts[4]==='deactivate')record.is_active=false
    return structuredClone(record)
  })
  const {ui}=page
  await ui.flush();assert.equal(nodes(ui.tree).some(node=>node.type===page.Color),false)
  page.tab('菜色分類').props.onClick();await ui.flush()
  assert.equal(nodes(ui.tree).some(node=>node.type===page.Color),false)
  const callsBeforeSameTab=calls.length
  page.tab('菜色分類').props.onClick();await ui.flush()
  assert.ok(page.row(category.name),'clicking the selected tab must retain the loaded list')
  assert.equal(calls.length,callsBeforeSameTab,'the selected tab must not start another request')
  const createForm=nodes(ui.tree).find(node=>node.type==='form')
  assert.equal(nodes(createForm).filter(node=>node.type==='input').length,1)
  assert.equal(nodes(createForm).filter(node=>node.type==='fieldset').length,0)
  nodes(createForm).find(node=>node.type==='input').props.onChange({target:{value:'新分類'}});await ui.flush()
  await nodes(ui.tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}});await ui.flush()
  const created=JSON.parse(calls.find(call=>call.init?.method==='POST').init.body)
  assert.equal(created.name,'新分類');assert.equal('background_color' in created,false)
  const edit=()=>nodes(page.row('新分類')).find(node=>node.type==='button'&&text(node)==='修改')
  edit().props.onClick();await ui.flush()
  await page.dialog().props.onSave('新分類','#FCE4EC');await ui.flush()
  assert.equal(records.dish.find(item=>item.id==='new').background_color,'#FCE4EC')
  const preview=()=>nodes(page.row('新分類')).find(node=>node.props?.className==='category-name-cell')
  assert.equal(preview().props.style['--dish-category-background'],'#FCE4EC')
  assert.match(text(preview()),/#FCE4EC/)
  nodes(page.row('新分類')).find(node=>node.type==='button'&&text(node)==='停用').props.onClick();await ui.flush()
  assert.equal(records.dish.find(item=>item.id==='new').is_active,false)
  assert.equal(preview().props.style['--dish-category-background'],'#FCE4EC')
  nodes(page.row('新分類')).find(node=>node.type==='button'&&text(node)==='↑ 上移').props.onClick();await ui.flush()
  assert.equal(preview().props.style['--dish-category-background'],'#FCE4EC')
  edit().props.onClick();await ui.flush();fail=true
  await page.dialog().props.onSave('新分類','#DCEDC8');await ui.flush()
  assert.ok(page.dialog().props.error)
  assert.equal(preview().props.style['--dish-category-background'],'#FCE4EC')
  fail=false;await page.dialog().props.onSave('新分類',null);await ui.flush()
  assert.equal(JSON.parse(calls.filter(call=>call.init?.method==='PATCH').at(-1).init.body).background_color,null)
  assert.equal(preview().props.style,undefined);assert.match(text(preview()),/中性/)
  page.tab('食材分類').props.onClick();await ui.flush();page.button('修改').props.onClick();await ui.flush()
  await page.dialog().props.onSave('食材改名','#BBDEFB');await ui.flush()
  assert.equal('background_color' in JSON.parse(calls.filter(call=>call.init?.method==='PATCH').at(-1).init.body),false)
})

test('failed dish request cannot display previous ingredient rows; safe status/path and retry preserve the error', async () => {
  let fail=true
  const calls=[],page=management(async(path,init)=>{
    calls.push({path,init})
    if(path.includes('/ingredient'))return {items:[{...category,id:'ingredient',name:'合成食材分類'}],pagination:{total:1}}
    if(fail)throw Object.assign(Error('SERVER_PRIVATE_DETAIL_SENTINEL'),{status:500})
    return {items:[category],pagination:{total:1}}
  })
  await page.ui.flush();assert.ok(page.row('合成食材分類'))
  page.tab('菜色分類').props.onClick();await page.ui.flush()
  assert.equal(page.row('合成食材分類'),undefined)
  assert.equal(page.row(category.name),undefined)
  assert.match(text(page.ui.tree),/HTTP 500/)
  assert.match(text(page.ui.tree),/\/categories\/dish\?page_size=100/)
  assert.match(text(page.ui.tree),/Migration/)
  assert.doesNotMatch(text(page.ui.tree),/SERVER_PRIVATE_DETAIL_SENTINEL/)
  assert.equal(nodes(page.ui.tree).some(node=>node.type===page.Empty),false)
  assert.ok(page.button('重新載入分類'))
  fail=false;page.button('重新載入分類').props.onClick();await page.ui.flush()
  assert.ok(page.row(category.name));assert.doesNotMatch(text(page.ui.tree),/分類載入失敗/)
  assert.equal(calls.filter(call=>call.path.includes('/dish')).length,2)
  assert.equal(calls.some(call=>call.init?.method),false)
})

test('a later page failing never publishes partial categories, and a failed reload hides stale rows', async () => {
  let mode='partial'
  const first=Array.from({length:100},(_,i)=>({...category,id:String(i)}))
  const page=management(async path=>{
    if(path.includes('/ingredient'))return {items:[],pagination:{total:0}}
    if(mode==='success')return {items:[category],pagination:{total:1}}
    if(path.includes('page=2')||mode==='reload-failure')throw Object.assign(Error('private'),{status:403})
    return {items:first,pagination:{total:101}}
  })
  await page.ui.flush();page.tab('菜色分類').props.onClick();await page.ui.flush()
  assert.equal(page.row(category.name),undefined)
  assert.match(text(page.ui.tree),/page=2/);assert.match(text(page.ui.tree),/HTTP 403/)
  mode='success';page.button('重新載入分類').props.onClick();await page.ui.flush()
  assert.ok(page.row(category.name))
  // Re-entering the same category triggers a fresh read after another tab.
  mode='reload-failure';page.tab('食材分類').props.onClick();await page.ui.flush();page.tab('菜色分類').props.onClick();await page.ui.flush()
  assert.equal(page.row(category.name),undefined);assert.match(text(page.ui.tree),/HTTP 403/)
})

test('category loader distinguishes response shape, pagination change, authentication and network failures', async () => {
  for(const bad of [{items:null},{items:[{}]},{items:[],pagination:{total:'1'}}]){
    await assert.rejects(display.loadDishCategories(async()=>bad),error=>{
      assert.equal(error.code,'format');assert.match(display.categoryLoadMessage(error,'fallback'),/格式不符/);return true
    })
  }
  for(const status of [401,403,500]){
    await assert.rejects(display.loadDishCategories(async()=>{throw {status,message:'SECRET_DETAIL'}}),error=>{
      assert.equal(error.status,status);assert.match(display.categoryLoadMessage(error,'fallback'),new RegExp(`HTTP ${status}`));assert.doesNotMatch(display.categoryLoadMessage(error,'fallback'),/SECRET_DETAIL/);return true
    })
  }
  await assert.rejects(display.loadDishCategories(async()=>{throw new TypeError('private URL')}),error=>{
    assert.match(display.categoryLoadMessage(error,'fallback'),/Backend 連線/);assert.doesNotMatch(display.categoryLoadMessage(error,'fallback'),/private URL/);return true
  })
})

test('edit dialog retains current color, selection stays local until save, and non-dish dialogs have no color control', async () => {
  const Color=()=>{},saved=[],props={category,kind:'dish',busy:false,error:'',onClose(){},onSave:async(...args)=>saved.push(args)}
  const ui=hooks(react=>load('features/categories/CategoriesPage.tsx',react,{'./CategoryColorPicker':{CategoryColorPicker:Color}},'\nexports.TestDialog=CategoryDialog;').TestDialog,props)
  let picker=nodes(ui.tree).find(node=>node.type===Color)
  assert.equal(picker.props.value,'#BBDEFB')
  picker.props.onChange(null);await ui.flush()
  assert.equal(saved.length,0)
  await nodes(ui.tree).find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  assert.deepEqual(saved,[['原分類',null]])
  ui.update({...props,kind:'menu'})
  assert.equal(nodes(ui.tree).some(node=>node.type===Color),false)
})

test('late paginated category metadata cannot replace a newer meal load or upgrade an old token', async () => {
  let finishOld,categoryLoads=0,slotLoads=0
  const oldPage=new Promise(resolve=>{finishOld=resolve}),calls=[]
  const controller=new MealEditorController('menu','2026-11-09','meal',async(path,init)=>{
    calls.push({path,init})
    if(init)return {menu:{id:'menu'}}
    if(path.includes('meal-slots'))return {menu_date:'2026-11-09',menu_meal_type_id:'meal',notes:null,dishes:[],slot_fingerprint:(++slotLoads===1?'a':'b').repeat(64),dish_category_ids:{}}
    if(path.endsWith('editor'))return {menu:{id:'menu'},meal_types:[{id:'meal',is_active:true}],meal_type_columns:[]}
    if(path.includes('page=2'))return oldPage
    if(++categoryLoads===1)return {items:Array.from({length:100},(_,i)=>({...category,id:`old-${i}`})),pagination:{total:101}}
    return {items:[{...category,background_color:'#FCE4EC'}],pagination:{total:1}}
  })
  const oldLoad=controller.load()
  for(let i=0;i<15;i++)await Promise.resolve()
  assert.ok(calls.some(call=>call.path.includes('page=2')))
  await controller.load()
  finishOld({items:[{...category,id:'old-last'}],pagination:{total:101}});await oldLoad
  assert.equal(controller.getSnapshot().categories.length,1)
  assert.equal(controller.getSnapshot().categories[0].background_color,'#FCE4EC')
  await controller.save()
  assert.equal(JSON.parse(calls.find(call=>call.init).init.body).expected_slot_fingerprint,'b'.repeat(64))
})
