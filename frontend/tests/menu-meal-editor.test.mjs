import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import vm from 'node:vm'
import test from 'node:test'
import ts from 'typescript'
import { MealEditorController } from '../src/features/menus/mealEditorController.ts'

const date = '2026-09-01'
const makeDish = (id, order) => ({ id, dish_id: `dish-${id}`, menu_meal_type_column_id: null, dish_name: id, diner_count: 20, notes: null, sort_order: order })
function fixtures() {
  const slot = { menu_day_id: 'day', menu_date: date, menu_meal_type_id: 'lunch', notes: null, dishes: [makeDish('a', 1), makeDish('b', 2)], slot_fingerprint: 'a'.repeat(64) }
  const aggregate = { menu: { id: 'menu' }, dates: [date], editor_fingerprint: 'b'.repeat(64), meal_types: [{ id: 'lunch', name: '午餐', is_active: true }, { id: 'dinner', name: '晚餐', is_active: true }], meal_type_columns: [{ id: 'main', menu_meal_type_id: 'lunch', sort_order: 1 }], slots: [slot] }
  return { slot, aggregate }
}
function setup() {
  const data = fixtures(), calls = []
  const controls = { saveError: null, saveWait: null, loadError: false, search: null }
  const request = async (path, init) => {
    calls.push({ path, init })
    if (init?.method === 'PUT') {
      if (controls.saveWait) await controls.saveWait
      if (controls.saveError) throw controls.saveError
      return structuredClone(data.aggregate)
    }
    if (path.startsWith('/dishes?')) return controls.search ? controls.search(path) : { items: [], pagination: { total: 0 } }
    if (controls.loadError) throw new Error('offline')
    if (path.includes('/meal-slots/')) return structuredClone(data.slot)
    if (path.endsWith('/editor')) return structuredClone(data.aggregate)
    return { items: [{ id: 'category', name: '主菜' }] }
  }
  return { ...data, calls, controls, request, controller: new MealEditorController('menu', date, 'lunch', request) }
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

test('shared controller loads the exact slot before metadata and saves only that slot with its fingerprint', async () => {
  const { controller, calls } = setup()
  await controller.load()
  assert.equal(calls[0].path, `/menus/menu/meal-slots/lunch/${date}`)
  assert.equal(controller.getSnapshot().dirty, false)
  controller.updateDish(0, { diner_count: 75, notes: '新備註', menu_meal_type_column_id: 'main' })
  const saved = await controller.save()
  const call = calls.find(item => item.init?.method === 'PUT'), payload = JSON.parse(call.init.body)
  assert.equal(call.path, calls[0].path)
  assert.equal(payload.expected_slot_fingerprint, 'a'.repeat(64))
  assert.equal(payload.dishes[0].id, 'a')
  assert.equal(payload.dishes[0].diner_count, 75)
  assert.equal(payload.dishes[0].notes, '新備註')
  assert.equal(payload.dishes[0].menu_meal_type_column_id, 'main')
  assert.equal('slots' in payload, false)
  assert.equal('editor_fingerprint' in payload, false)
  assert.equal(saved.menu.id, 'menu')
  assert.equal(controller.getSnapshot().dirty, false)
})

test('draft supports notes, add, duplicate rejection, remove and normalized ordering without mutating source', async () => {
  const { controller, slot } = setup()
  await controller.load()
  controller.change({ ...controller.getSnapshot().slot, notes: '本餐備註' })
  controller.add({ id: 'c', name: '新菜', code: 'C', is_active: true })
  controller.add({ id: 'c', name: '新菜', is_active: true })
  assert.equal(controller.getSnapshot().slot.dishes.length, 3)
  controller.move(2, -1)
  assert.deepEqual(controller.getSnapshot().slot.dishes.map(item => item.dish_name), ['a', '新菜', 'b'])
  controller.remove(0)
  assert.deepEqual(controller.getSnapshot().slot.dishes.map(item => item.sort_order), [1, 2])
  assert.equal(controller.getSnapshot().slot.notes, '本餐備註')
  assert.equal(controller.getSnapshot().dirty, true)
  assert.equal(slot.dishes.length, 2)
})

test('column change uses existing visual placement and preserves menu dish identity', async () => {
  const { controller } = setup(); await controller.load()
  controller.updateDish(1, { menu_meal_type_column_id: 'main' })
  assert.deepEqual(controller.getSnapshot().slot.dishes.map(item => item.id), ['b', 'a'])
  assert.deepEqual(controller.getSnapshot().slot.dishes.map(item => item.sort_order), [1, 2])
})

test('save failure retains all input and dirty state and permits retry', async () => {
  const { controller, controls } = setup(); await controller.load()
  controller.updateDish(0, { diner_count: 99, notes: '不可丟失' })
  controls.saveError = new Error('offline')
  assert.equal(await controller.save(), null)
  assert.equal(controller.getSnapshot().slot.dishes[0].notes, '不可丟失')
  assert.equal(controller.getSnapshot().dirty, true)
  assert.equal(controller.getSnapshot().saving, false)
  assert.equal(controller.getSnapshot().conflict, false)
  controls.saveError = null
  assert.ok(await controller.save())
})

test('409 preserves draft, blocks resubmission, and explicit reload adopts new fingerprint', async () => {
  const { controller, controls, calls, slot } = setup(); await controller.load()
  controller.updateDish(0, { diner_count: 99 })
  controls.saveError = { status: 409, detail: { code: 'MENU_SLOT_VERSION_CONFLICT' } }
  await controller.save()
  assert.equal(controller.getSnapshot().slot.dishes[0].diner_count, 99)
  assert.equal(controller.getSnapshot().conflict, true)
  assert.match(controller.getSnapshot().error, /未覆蓋伺服器資料/)
  await controller.save()
  assert.equal(calls.filter(call => call.init?.method === 'PUT').length, 1)
  slot.slot_fingerprint = 'c'.repeat(64); slot.dishes[0].diner_count = 80
  await controller.load()
  assert.equal(controller.getSnapshot().dirty, false)
  assert.equal(controller.getSnapshot().slot.dishes[0].diner_count, 80)
  controls.saveError = null
  await controller.save()
  assert.equal(JSON.parse(calls.at(-1).init.body).expected_slot_fingerprint, 'c'.repeat(64))
})

test('failed reload does not discard a conflicted draft or upgrade its token', async () => {
  const { controller, controls } = setup(); await controller.load()
  controller.updateDish(0, { diner_count: 99 })
  controls.saveError = { status: 409 }; await controller.save()
  controls.loadError = true; await controller.load()
  assert.equal(controller.getSnapshot().slot.dishes[0].diner_count, 99)
  assert.equal(controller.getSnapshot().dirty, true)
  assert.equal(controller.getSnapshot().conflict, true)
})

test('pending save prevents duplicate requests and edits', async () => {
  const { controller, controls, calls } = setup(); await controller.load()
  const wait = deferred(); controls.saveWait = wait.promise
  const first = controller.save(); const second = await controller.save()
  controller.updateDish(0, { diner_count: 900 })
  assert.equal(second, null)
  assert.equal(controller.getSnapshot().slot.dishes[0].diner_count, 20)
  wait.resolve(); await first
  assert.equal(calls.filter(call => call.init?.method === 'PUT').length, 1)
})

test('invalid counts, duplicate columns and notes are rejected before the API', async () => {
  const { controller, calls } = setup(); await controller.load()
  controller.updateDish(0, { diner_count: -1 }); assert.equal(await controller.save(), null)
  controller.updateDish(0, { diner_count: 1, notes: 'x'.repeat(1001) }); assert.equal(await controller.save(), null)
  controller.updateDish(0, { notes: null, menu_meal_type_column_id: 'main' })
  controller.updateDish(1, { menu_meal_type_column_id: 'main' }); assert.equal(await controller.save(), null)
  assert.equal(calls.filter(call => call.init?.method === 'PUT').length, 0)
})

test('switching date or meal uses a separate session; disposed load cannot publish later', async () => {
  const wait = deferred(), { slot } = fixtures()
  const controller = new MealEditorController('menu', date, 'lunch', () => wait.promise)
  const load = controller.load(); controller.dispose(); wait.resolve(slot); await load
  assert.equal(controller.getSnapshot().slot, null)
  const calls = []
  const other = new MealEditorController('menu', '2026-09-02', 'dinner', async path => { calls.push(path); throw new Error('stop') })
  await other.load()
  assert.deepEqual(calls, ['/menus/menu/meal-slots/dinner/2026-09-02'])
})

test('search passes keyword category and pagination and ignores old responses', async () => {
  const { controller, controls, calls } = setup(); await controller.load()
  const wait = deferred()
  controls.search = path => path.includes('search=old') ? wait.promise : { items: [{ id: 'new' }], pagination: { total: 1 } }
  const first = controller.search('old', 'category', 2)
  await controller.search('new', 'category', 1)
  wait.resolve({ items: [{ id: 'old' }], pagination: { total: 99 } }); await first
  assert.equal(controller.getSnapshot().results[0].id, 'new')
  assert.match(calls.find(call => call.path.includes('search=old')).path, /page=2.*category_id=category/)
  await controller.search('', '', 1)
  assert.deepEqual(controller.getSnapshot().results, [])
})

test('empty slot null menu_day_id stays null and inactive meal cannot add dishes', async () => {
  const { controller, slot, aggregate, calls } = setup()
  slot.menu_day_id = null; slot.dishes = []; aggregate.meal_types[0].is_active = false
  await controller.load(); controller.add({ id: 'new', is_active: true })
  assert.equal(controller.getSnapshot().slot.dishes.length, 0)
  await controller.save()
  assert.equal(JSON.parse(calls.at(-1).init.body).menu_day_id, null)
})

// Exercise the actual dialog hooks and callbacks without adding a DOM test dependency.
function dialogHarness(request) {
  let hooks = [], cursor = 0, effects = [], tree, component, props, disposed = false
  const dirty = new Map(), eventListeners = new Map(), timers = new Set()
  const depsEqual = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]))
  const effect = (callback, deps) => {
    const index = cursor++, previous = hooks[index]
    if (!previous || !depsEqual(previous.deps, deps)) effects.push(() => { previous?.cleanup?.(); hooks[index] = { deps, cleanup: callback() } })
  }
  const render = () => {
    if (disposed) return
    cursor = 0; effects = []; tree = component(props)
    const pending = effects; effects = []; pending.forEach(run => run())
  }
  const schedule = () => queueMicrotask(render)
  const react = {
    useMemo: (factory, deps) => { const index = cursor++; if (!hooks[index] || !depsEqual(hooks[index].deps, deps)) hooks[index] = { deps, value: factory() }; return hooks[index].value },
    useRef: value => { const index = cursor++; return hooks[index] ??= { current: value } },
    useState: value => { const index = cursor++; if (!hooks[index]) hooks[index] = { value }; return [hooks[index].value, value => { hooks[index].value = typeof value === 'function' ? value(hooks[index].value) : value; schedule() }] },
    useEffect: effect,
    useSyncExternalStore: (subscribe, getSnapshot) => { effect(() => subscribe(schedule), [subscribe]); return getSnapshot() },
  }
  const jsx = (type, props, key) => ({ type, props: props ?? {}, key })
  const source = readFileSync(new URL('../src/features/menus/MenuMealEditorDialog.tsx', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const exports = {}, panel = () => {}, opener = { focus() {} }
  const context = { exports, queueMicrotask, document: { activeElement: opener }, window: {
    setTimeout: fn => { const timer = setTimeout(fn, 0); timers.add(timer); return timer }, clearTimeout: timer => { clearTimeout(timer); timers.delete(timer) },
    addEventListener: (name, listener) => eventListeners.set(name, listener), removeEventListener: (name, listener) => { if (eventListeners.get(name) === listener) eventListeners.delete(name) },
  }, require: path => {
    if (path === 'react') return react
    if (path === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'fragment' }
    if (path.includes('api/client')) return { apiRequest: request }
    if (path.includes('NavigationBlocker')) return { useEditorDirty: value => {
      const owner = react.useRef(Symbol()).current
      effect(() => { dirty.set(owner, value); return () => dirty.delete(owner) }, [value])
      return () => dirty.delete(owner)
    } }
    if (path.includes('ui/Page')) return { Feedback: 'Feedback', LoadingState: 'LoadingState' }
    if (path === './MenuEditorPanel') return { MenuEditorPanel: panel }
    if (path === './mealEditorController') return { MealEditorController }
    throw new Error(path)
  } }
  vm.runInNewContext(compiled, context)
  const root = exports.MenuMealEditorDialog({ menuId: 'menu', date, mealTypeId: 'lunch', onSaved() {}, onClose() {} })
  component = root.type; props = root.props; render()
  function nodes(value) { return Array.isArray(value) ? value.flatMap(item => nodes(item)) : value && typeof value === 'object' ? [value, ...nodes(value.props?.children)] : [] }
  return {
    async settle() { await new Promise(done => setTimeout(done, 5)) },
    setProps(changes) { props = { ...props, ...changes }; render() },
    panel: () => nodes(tree).find(node => node.type === panel)?.props,
    confirm: () => nodes(tree).find(node => node.props?.className === 'secondary-danger'),
    dirty: () => [...dirty.values()].some(Boolean),
    escape() { eventListeners.get('keydown')?.({ key: 'Escape', preventDefault() {} }) },
    close() { disposed = true; hooks.forEach(hook => hook?.cleanup?.()); timers.forEach(clearTimeout) },
  }
}

test('dialog dirty close needs explicit confirmation; cancelling preserves input', async () => {
  const { request } = setup(), ui = dialogHarness(request); let closed = 0
  try {
    ui.setProps({ onClose: () => closed++ }); await ui.settle()
    ui.panel().onDishChange(0, { notes: '保留輸入' }); await ui.settle()
    assert.equal(ui.dirty(), true)
    ui.panel().onClose(); await ui.settle(); assert.ok(ui.confirm()); assert.equal(closed, 0)
    ui.escape(); await ui.settle(); assert.equal(ui.confirm(), undefined)
    assert.equal(ui.panel().slot.dishes[0].notes, '保留輸入')
    ui.panel().onClose(); await ui.settle(); ui.confirm().props.onClick(); await ui.settle()
    assert.equal(closed, 1); assert.equal(ui.dirty(), false)
  } finally { ui.close() }
})

test('dialog 409 keeps input, reload requires confirmation, and save returns authoritative aggregate', async () => {
  const { request, controls, slot } = setup(), ui = dialogHarness(request); let saved = null, closed = 0
  try {
    ui.setProps({ onSaved: value => { saved = value }, onClose: () => closed++ }); await ui.settle()
    ui.panel().onDishChange(0, { diner_count: 99 }); await ui.settle()
    controls.saveError = { status: 409 }; await ui.panel().onSave(); await ui.settle()
    assert.equal(ui.panel().blocked, true); assert.equal(closed, 0); assert.equal(ui.panel().slot.dishes[0].diner_count, 99)
    ui.panel().onReload(); await ui.settle(); assert.ok(ui.confirm())
    slot.dishes[0].diner_count = 88; slot.slot_fingerprint = 'f'.repeat(64)
    ui.confirm().props.onClick(); await ui.settle()
    assert.equal(ui.panel().slot.dishes[0].diner_count, 88); assert.equal(ui.panel().blocked, false)
    controls.saveError = null; await ui.panel().onSave(); await ui.settle()
    assert.equal(saved.menu.id, 'menu'); assert.equal(closed, 1)
  } finally { ui.close() }
})

test('dialog removal is not applied until confirmed and preserves remaining dish data', async () => {
  const { request } = setup(), ui = dialogHarness(request)
  try {
    await ui.settle()
    ui.panel().onRemove(0); await ui.settle()
    assert.equal(ui.panel().slot.dishes.length, 2)
    ui.escape(); await ui.settle()
    assert.equal(ui.panel().slot.dishes[0].id, 'a')
    ui.panel().onRemove(0); await ui.settle(); ui.confirm().props.onClick(); await ui.settle()
    assert.deepEqual(ui.panel().slot.dishes.map(dish => [dish.id, dish.diner_count, dish.sort_order]), [['b', 20, 1]])
  } finally { ui.close() }
})

test('dialog failed save keeps notes and count and never invokes saved or close', async () => {
  const { request, controls } = setup(), ui = dialogHarness(request); let closed = 0, saved = 0
  try {
    ui.setProps({ onSaved: () => saved++, onClose: () => closed++ }); await ui.settle()
    ui.panel().onSlotNotes('本餐內容'); ui.panel().onDishChange(0, { diner_count: 65, notes: '菜色內容' }); await ui.settle()
    controls.saveError = new Error('offline'); await ui.panel().onSave(); await ui.settle()
    assert.equal(saved, 0); assert.equal(closed, 0)
    assert.equal(ui.panel().slot.notes, '本餐內容')
    assert.equal(ui.panel().slot.dishes[0].notes, '菜色內容')
    assert.equal(ui.panel().slot.dishes[0].diner_count, 65)
    assert.equal(ui.panel().saving, false); assert.equal(ui.dirty(), true)
  } finally { ui.close() }
})

test('dialog cannot close or submit twice while a save is pending', async () => {
  const { request, controls, calls } = setup(), ui = dialogHarness(request); let closed = 0
  const wait = deferred()
  try {
    ui.setProps({ onClose: () => closed++ }); await ui.settle()
    controls.saveWait = wait.promise
    const first = ui.panel().onSave(); await ui.settle()
    assert.equal(ui.panel().saving, true)
    ui.panel().onClose(); ui.escape(); await ui.panel().onSave(); await ui.settle()
    assert.equal(closed, 0)
    assert.equal(calls.filter(call => call.init?.method === 'PUT').length, 1)
    wait.resolve(); await first; await ui.settle()
    assert.equal(closed, 1)
  } finally { wait.resolve(); ui.close() }
})

test('saved callback reports real dirty state only after success; cancel validation and 409 never report saved', async () => {
  const {request,controls}=setup(),ui=dialogHarness(request),results=[]
  try{
    ui.setProps({onSaved:(_aggregate,result)=>results.push(result.changed)});await ui.settle()
    await ui.panel().onSave();await ui.settle();assert.deepEqual(results,[false])
    ui.panel().onDishChange(0,{diner_count:99});await ui.settle()
    controls.saveError={status:409};await ui.panel().onSave();await ui.settle();assert.deepEqual(results,[false])
    ui.panel().onReload();await ui.settle();ui.confirm().props.onClick();await ui.settle()
    controls.saveError=null
    ui.panel().onDishChange(0,{diner_count:-1});await ui.settle()
    await ui.panel().onSave();await ui.settle();assert.deepEqual(results,[false])
    ui.panel().onDishChange(0,{diner_count:98});await ui.settle()
    await ui.panel().onSave();await ui.settle();assert.deepEqual(results,[false,true])
    ui.panel().onClose();await ui.settle();assert.deepEqual(results,[false,true])
  }finally{ui.close()}
})

test('parent integration reuses the shared dialog and preserves parent meal-type draft names', () => {
  const editor = readFileSync(new URL('../src/features/menus/MenuEditor.tsx', import.meta.url), 'utf8')
  assert.match(editor, /<MenuMealEditorDialog menuId=\{menu.id\} date=\{editing.date\} mealTypeId=\{editing.mealId\}/)
  assert.doesNotMatch(editor, /function saveMealDraft|setMealDraft\(/)
  assert.match(editor, /current\[meal.id\] !== previous.name \? current\[meal.id\] : meal.name/)
  const dialog = readFileSync(new URL('../src/features/menus/MenuMealEditorDialog.tsx', import.meta.url), 'utf8')
  assert.match(dialog, /key=\{`\$\{props.menuId\}:\$\{props.date\}:\$\{props.mealTypeId\}`\}/)
})

test('navigation blocker keeps another editor dirty when a child editor closes', () => {
  const source = readFileSync(new URL('../src/app/NavigationBlocker.tsx', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const exports = {}, jsx = (type, props) => ({ type, props }), refs = []
  vm.runInNewContext(compiled, { exports, window: {}, require: path => path === 'react' ? {
    createContext: () => ({ Provider: 'provider' }), useCallback: fn => fn, useState: value => [value, () => {}], useEffect() {}, useRef: value => { const ref = { current: value }; refs.push(ref); return ref },
  } : path === 'react/jsx-runtime' ? { jsx, jsxs: jsx } : createRequire(import.meta.url)('../src/app/navigationPolicy.ts') })
  const provider = exports.NavigationBlockerProvider({ children: null }), { setEditorDirty, requestNavigation } = provider.props.value
  const parent = Symbol(), child = Symbol(); let navigated = 0
  setEditorDirty(true, parent); setEditorDirty(true, child); setEditorDirty(false, child)
  requestNavigation(() => navigated++); assert.equal(navigated, 0)
  setEditorDirty(false, parent); requestNavigation(() => navigated++); assert.equal(navigated, 1)
})
