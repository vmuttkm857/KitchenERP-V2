import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import {canAutoApplyMealSync,captureAdjustmentScroll,prepareAdjustmentMealEdit,restoreAdjustmentScroll,validAdjustmentMealTarget} from '../src/features/order_adjustments/mealEditing.ts'
import * as editor from '../src/features/order_adjustments/editor.ts'
import * as matrix from '../src/features/order_adjustments/matrix.ts'
import * as view from '../src/features/order_adjustments/view.ts'
import {mealSectionTone} from '../src/features/menus/mealSectionTone.ts'
import {MealEditorController} from '../src/features/menus/mealEditorController.ts'

const day='2026-09-01',target={menuId:'menu-a',date:day,mealTypeId:'meal-a'}
function fixture(){
  const menu=id=>({menu_id:id,menu_name:id,start_date:day,end_date:'2026-09-07',is_active:true})
  const layout=id=>({menu:{id,is_active:true},dates:Array.from({length:7},(_,i)=>`2026-09-0${i+1}`),meal_types:[{id:`meal-${id.at(-1)}`,menu_id:id,name:'午餐',sort_order:1,is_active:true}],meal_type_columns:[],slots:[{menu_date:day,menu_meal_type_id:`meal-${id.at(-1)}`,notes:null,dishes:[{id:'menu-dish',dish_id:'dish',diner_count:20,sort_order:1,menu_meal_type_column_id:null,notes:null}]}]})
  const line={id:'line',source_line_key:'menu-dish:recipe-line',source_dish_id:'dish',source_dish_ingredient_id:'recipe-line',source_ingredient_id:'ingredient',source_menu_id:'menu-a',source_menu_day_id:'day',source_meal_type_id:'meal-a',meal_type_name_snapshot:'午餐',meal_type_sort_order_snapshot:1,source_menu_dish_id:'menu-dish',dish_name_snapshot:'雞腿',diner_count_snapshot:20,menu_dish_sort_order_snapshot:1,source_menu_meal_type_column_id:null,dish_ingredient_sort_order_snapshot:1,requirement_date:day,system_quantity:'2',system_unit:'kg',adjusted_quantity:null,adjusted_unit:null,effective_quantity:'2',effective_unit:'kg',review_required:false,stale_reasons:[],ingredient_name_snapshot:'雞肉'}
  return {detail:{id:'sheet',status:'draft',purchase_locked:false,lock_version:1,source_fingerprint:'a'.repeat(64),revision:1,criteria:{menu_ids:['menu-a','menu-b'],start_date:day,end_date:'2026-09-07'},source_menus:[menu('menu-a'),menu('menu-b')],lines:[line],warnings:[],stale:false,created_at:day,updated_at:day},layouts:{'menu-a':layout('menu-a'),'menu-b':layout('menu-b')}}
}

function safePreview(detail=fixture().detail){
  const line=detail.lines[0],snapshot={line_id:line.id,source_line_key:line.source_line_key,source_menu_dish_id:line.source_menu_dish_id,source_dish_id:line.source_dish_id,source_dish_ingredient_id:line.source_dish_ingredient_id,source_ingredient_id:line.source_ingredient_id,dish_name:line.dish_name_snapshot,ingredient_name:line.ingredient_name_snapshot,system_quantity:line.system_quantity,system_unit:line.system_unit,adjusted_quantity:line.adjusted_quantity,adjusted_unit:line.adjusted_unit,effective_quantity:line.effective_quantity,effective_unit:line.effective_unit}
  return {sheet_id:detail.id,status:'draft',lock_version:detail.lock_version,saved_source_fingerprint:detail.source_fingerprint,preview_source_fingerprint:'b'.repeat(64),changed:true,summary:{added_dishes:0,removed_dishes:0,possible_dish_replacements:0,added_ingredients:0,removed_ingredients:0,changed_lines:1,unit_conflicts:0},added_dishes:[],removed_dishes:[],possible_dish_replacements:[],added_ingredients:[],removed_ingredients:[],unit_conflicts:[],line_changes:[{source_line_key:line.source_line_key,previous:snapshot,current:{...snapshot,line_id:undefined,system_quantity:'3'},preserves_adjustment:true,requires_confirmation:false,change_types:['diner_count_changed','reference_quantity_changed']}]}
}
function riskyPreview(detail=fixture().detail){
  const preview=safePreview(detail),old=preview.line_changes[0].previous
  preview.line_changes=[];preview.summary.changed_lines=0
  preview.removed_ingredients=[{source_line_key:null,previous:old,current:null,preserves_adjustment:false,requires_confirmation:true}];preview.summary.removed_ingredients=1
  return preview
}

test('meal target uses menu UUID, date and meal UUID including empty recipe slots',()=>{
  const {detail,layouts}=fixture()
  assert.equal(validAdjustmentMealTarget(detail,target,layouts['menu-a']),true)
  assert.equal(validAdjustmentMealTarget(detail,{menuId:'menu-b',date:day,mealTypeId:'meal-b'},layouts['menu-b']),true)
  assert.equal(validAdjustmentMealTarget(detail,{...target,menuId:'menu-b'},layouts['menu-a']),false)
  assert.equal(validAdjustmentMealTarget(detail,{...target,mealTypeId:'same-name-wrong-id'},layouts['menu-a']),false)
  assert.equal(validAdjustmentMealTarget(detail,{...target,date:'2026-10-01'},layouts['menu-a']),false)
  assert.equal(validAdjustmentMealTarget(detail,target,undefined),false)
  detail.lines=[]
  assert.equal(validAdjustmentMealTarget(detail,target,layouts['menu-a']),true)
})

test('draft stale remains editable but confirmed cancelled purchase-locked or unknown capabilities fail closed',()=>{
  const {detail,layouts}=fixture()
  assert.equal(validAdjustmentMealTarget({...detail,stale:true},target,layouts['menu-a']),true)
  for(const change of [{status:'confirmed'},{status:'cancelled'},{purchase_locked:true},{purchase_locked:undefined}])assert.equal(validAdjustmentMealTarget({...detail,...change},target,layouts['menu-a']),false)
})

test('entry awaits existing draft save then refresh before opening with latest lock version',async()=>{
  const {detail,layouts}=fixture(),order=[]
  let release;const pending=new Promise(resolve=>{release=resolve})
  const preparing=prepareAdjustmentMealEdit({detail,target,layout:layouts['menu-a'],dirty:true,invalid:false,saveBlocked:false,sourceUnverified:false,
    save:async()=>{order.push('save');await pending;order.push('saved');return {...detail,lock_version:2}},refresh:async()=>{order.push('refresh');return {...detail,lock_version:2}}})
  await Promise.resolve();assert.deepEqual(order,['save'])
  release();assert.equal((await preparing).lock_version,2)
  assert.deepEqual(order,['save','saved','refresh'])
})

test('failed draft save never opens or refreshes and dirty stale input never saves',async()=>{
  const {detail,layouts}=fixture();let refreshes=0,saves=0
  const options={detail,target,layout:layouts['menu-a'],dirty:true,invalid:false,saveBlocked:false,sourceUnverified:false,save:async()=>{saves++;return null},refresh:async()=>{refreshes++;return detail}}
  assert.equal(await prepareAdjustmentMealEdit(options),null)
  assert.equal(refreshes,0)
  for(const change of [{detail:{...detail,stale:true}},{invalid:true},{saveBlocked:true},{sourceUnverified:true}])await assert.rejects(prepareAdjustmentMealEdit({...options,...change}))
  assert.equal(saves,1)
})

test('fresh status revalidation rejects confirmation or procurement locks before mounting',async()=>{
  const {detail,layouts}=fixture()
  for(const change of [{status:'confirmed'},{purchase_locked:true}])await assert.rejects(prepareAdjustmentMealEdit({detail,target,layout:layouts['menu-a'],dirty:false,invalid:false,saveBlocked:false,sourceUnverified:false,save:async()=>{throw Error('must not save')},refresh:async()=>({...detail,...change})}))
})

// Run the real detail-view hooks and callbacks, mocking only API/UI boundaries.
function harness(initial=fixture()){
  let hooks=[],index=0,pending=[],tree,props,unmounted=false,exports
  const calls=[],api={saveFail:false,refreshFail:false,previewFail:false,syncFail:null,pendingSave:null,pendingPreview:null,pendingSync:null,preview:null,detail:structuredClone(initial.detail),layouts:initial.layouts}
  const scroll={scrollLeft:640,scrollTop:320},viewport={scrollX:0,scrollY:470,scrollTo(x,y){this.scrollX=x;this.scrollY=y}}
  const root={querySelector:()=>scroll}
  class ApiError extends Error{constructor(status,detail){super('API failed');this.status=status;this.detail=detail}}
  const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]))
  const render=()=>{if(unmounted)return;index=0;pending=[];tree=exports.OrderingAdjustmentDetailView(props);tree.props.ref.current=root;const effects=pending;pending=[];effects.forEach(run=>run())}
  const schedule=()=>queueMicrotask(render)
  const react={
    useState:initial=>{const i=index++;hooks[i]??={value:typeof initial==='function'?initial():initial};return [hooks[i].value,next=>{hooks[i].value=typeof next==='function'?next(hooks[i].value):next;schedule()}]},
    useRef:initial=>{const i=index++;return hooks[i]??={current:initial}},
    useCallback:(fn,deps)=>{const i=index++;if(!hooks[i]||!equal(hooks[i].deps,deps))hooks[i]={deps,fn};return hooks[i].fn},
    useEffect:(effect,deps)=>{const i=index++,old=hooks[i];if(!old||!equal(old.deps,deps))pending.push(()=>{old?.cleanup?.();hooks[i]={deps,cleanup:effect()}})},
  }
  react.useLayoutEffect=react.useEffect
  const jsx=(type,props,key)=>({type,props:props??{},key}),dialog=()=>{}
  const apiMethods={
    getOrderingAdjustmentMenuLayout:async id=>{calls.push(['layout',id]);return api.layouts[id]},
    getOrderingAdjustment:async id=>{calls.push(['get',id]);if(api.refreshFail)throw new ApiError(503,null);return structuredClone(api.detail)},
    updateOrderingAdjustmentLines:async(id,payload)=>{calls.push(['save',id,payload]);if(api.pendingSave)await api.pendingSave;if(api.saveFail)throw new ApiError(409,{code:'LOCK_VERSION_CONFLICT'});api.detail={...api.detail,lock_version:api.detail.lock_version+1,lines:api.detail.lines.map(line=>{const change=payload.lines.find(item=>item.id===line.id);return change?{...line,...change,effective_quantity:change.adjusted_quantity??line.system_quantity,effective_unit:change.adjusted_unit??line.system_unit}:line})};return structuredClone(api.detail)},
    previewOrderingAdjustmentSync:async(id,version)=>{calls.push(['preview',id,version]);const preview=api.preview??safePreview(api.detail);if(api.pendingPreview)await api.pendingPreview;if(api.previewFail)throw new ApiError(503,null);return structuredClone(preview)},
    applyOrderingAdjustmentSync:async(id,payload)=>{calls.push(['sync',id,payload]);if(api.pendingSync)await api.pendingSync;if(api.syncFail)throw new ApiError(409,{code:api.syncFail});api.detail={...api.detail,stale:false,source_fingerprint:payload.expected_source_fingerprint,lock_version:api.detail.lock_version+1,lines:api.detail.lines.map(line=>({...line,system_quantity:'3',effective_quantity:line.adjusted_quantity??'3',effective_unit:line.adjusted_unit??line.system_unit}))};return structuredClone(api.detail)},
  }
  const ui={Feedback:'Feedback',LoadingState:'Loading',EmptyState:'Empty',PageHeader:'PageHeader',TableFrame:'TableFrame'}
  const code=readFileSync(new URL('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx',import.meta.url),'utf8')+'\nexport {OrderingAdjustmentDetailView,AdjustmentWeeklyMatrix,SyncAdjustmentDialog}'
  exports={}
  vm.runInNewContext(ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,console,window:viewport,require:path=>{
    if(path==='react')return react
    if(path==='react/jsx-runtime')return {jsx,jsxs:jsx,Fragment:'Fragment'}
    if(path.includes('api/client'))return {ApiError}
    if(path.includes('NavigationBlocker'))return {useEditorDirty:()=>()=>{}}
    if(path.includes('ui/Page'))return ui
    if(path.endsWith('/MenuMealEditorDialog'))return {MenuMealEditorDialog:dialog}
    if(path==='./api')return apiMethods
    if(path==='./editor')return editor
    if(path==='./matrix')return matrix
    if(path==='./view')return view
    if(path==='./mealEditing')return {canAutoApplyMealSync,captureAdjustmentScroll,prepareAdjustmentMealEdit,restoreAdjustmentScroll,validAdjustmentMealTarget}
    if(path.endsWith('/mealSectionTone'))return {mealSectionTone}
    return {}
  }})
  props={detail:initial.detail,onDetailChange:detail=>{props={...props,detail};schedule()},onBack:()=>{calls.push(['back'])}}
  render()
  const nodes=value=>Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props?.children)]:[]
  const text=value=>Array.isArray(value)?value.map(text).join(''):value&&typeof value==='object'?text(value.props?.children):typeof value==='string'?value:''
  return {api,calls,dialog,scroll,viewport,exports,async settle(){await new Promise(done=>setTimeout(done,5))},
    async saved(aggregate=api.layouts['menu-a'],changed=true){api.detail={...api.detail,stale:changed};this.mealDialog().props.onSaved(aggregate,{changed});await this.settle()},
    detail:()=>props.detail,
    setDetail(detail){props={...props,detail};render()},
    matrix:()=>nodes(tree).find(node=>node.type===exports.AdjustmentWeeklyMatrix),
    mealDialog:()=>nodes(tree).find(node=>node.type===dialog),
    syncDialog:()=>nodes(tree).find(node=>node.type?.name==='SyncAdjustmentDialog'),
    button:label=>nodes(tree).find(node=>node.type==='button'&&text(node)===label),
    texts:()=>text(tree),
    matrixNodes(){return nodes(exports.AdjustmentWeeklyMatrix(this.matrix().props))},
    close(){unmounted=true;hooks.forEach(hook=>hook?.cleanup?.())},
  }
}

test('matrix renders one edit button per date and meal, not per dish, including empty meals',async()=>{
  const f=fixture();f.layouts['menu-a'].meal_type_columns=[{id:'main',name:'主菜',menu_meal_type_id:'meal-a',sort_order:1},{id:'side',name:'副菜',menu_meal_type_id:'meal-a',sort_order:2}]
  const ui=harness(f)
  try{await ui.settle();const buttons=ui.matrixNodes().filter(node=>node.props?.title==='編輯本餐');assert.equal(buttons.length,7);assert.equal(ui.matrix().props.matrix.meals[0].rows.length,2);assert.ok(buttons.every(button=>!button.props.disabled))}finally{ui.close()}
})

test('meal-entry hidden label has a local containing block without clipping the document',()=>{
  const css=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')
  const entry=css.match(/\.ordering-meal-edit-entry\{([^}]+)\}/)?.[1]
  assert.match(entry,/position:\s*relative/)
  assert.match(css,/\.ordering-meal-edit-entry \.sr-only\{position:absolute/)
  assert.match(css,/\.ordering-adjustment-matrix\{[^}]*overflow:auto/)
  const page=readFileSync(new URL('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx',import.meta.url),'utf8')
  assert.match(page,/aria-label=\{`編輯本餐：/)
  assert.match(css,/\.ordering-meal-edit-entry button:focus-visible\{outline:/)
  assert.match(css,/@media\(max-width:400px\)\{\.app-layout:has\(\.ordering-adjustment-matrix\) \.topbar,\.app-layout:has\(\.ordering-adjustment-matrix\) \.account\{gap:\.35rem\}/)
})

test('entry auto-saves once and mounts shared dialog only after success',async()=>{
  const ui=harness();let release;ui.api.pendingSave=new Promise(resolve=>{release=resolve})
  try{
    await ui.settle();ui.matrix().props.onChange('line','3');await ui.settle()
    ui.matrix().props.onEditMeal(target);ui.matrix().props.onEditMeal(target);await ui.settle()
    assert.equal(ui.calls.filter(call=>call[0]==='save').length,1);assert.equal(ui.mealDialog(),undefined)
    assert.equal(ui.matrix().props.saving,true)
    release();await ui.settle()
    assert.equal(ui.mealDialog().props.menuId,'menu-a');assert.equal(ui.mealDialog().props.date,day);assert.equal(ui.mealDialog().props.mealTypeId,'meal-a')
    assert.equal(ui.mealDialog().props.orderingAdjustmentContext.lock_version,2)
    assert.equal(ui.matrix().props.values.line,'3')
  }finally{release();ui.close()}
})

test('failed draft save or refresh never opens dialog and preserves entered values',async()=>{
  for(const kind of ['saveFail','refreshFail']){
    const ui=harness();try{await ui.settle();ui.matrix().props.onChange('line','4');await ui.settle();ui.api[kind]=true;ui.matrix().props.onEditMeal(target);await ui.settle();assert.equal(ui.mealDialog(),undefined);assert.equal(ui.matrix().props.values.line,'4');assert.match(ui.texts(),/失敗|已在其他地方被修改/)}finally{ui.close()}
  }
})

test('switching menus opens only the active menu UUID and supports recipe-empty matrix',async()=>{
  const f=fixture();f.detail.lines=[];const ui=harness(f)
  try{await ui.settle();ui.button('menu-b').props.onClick();await ui.settle();const button=ui.matrixNodes().find(node=>node.props?.title==='編輯本餐');button.props.onClick();await ui.settle();assert.equal(ui.mealDialog().props.menuId,'menu-b');assert.equal(ui.mealDialog().props.mealTypeId,'meal-b')}finally{ui.close()}
})

test('risky saved meal automatically previews, cancel preserves stale inputs and permits further meals',async()=>{
  const ui=harness()
  try{
    await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle()
    ui.api.preview=riskyPreview(ui.api.detail);await ui.saved()
    assert.equal(ui.mealDialog(),undefined);assert.ok(ui.matrix());assert.equal(ui.matrix().props.readOnly,true)
    assert.match(ui.texts(),/原始菜單已變更，食材尚未同步/)
    assert.equal(ui.button('完成叫貨調整'),undefined)
    assert.equal(ui.calls.filter(call=>call[0]==='preview').length,1)
    assert.equal(ui.calls.some(call=>call[0]==='sync'),false)
    assert.ok(ui.syncDialog());ui.syncDialog().props.onCancel();await ui.settle()
    assert.equal(ui.matrix().props.canEditMeal({...target,date:'2026-09-02'}),true)
    ui.matrix().props.onEditMeal({...target,date:'2026-09-02'});await ui.settle()
    assert.equal(ui.mealDialog().props.date,'2026-09-02')
    ui.mealDialog().props.onClose();await ui.settle();assert.equal(ui.matrix().props.values.line,'2')
  }finally{ui.close()}
})

test('sync apply refreshes layout for the same sheet rather than depending only on detail id',async()=>{
  const f=fixture();f.detail.stale=true;const ui=harness(f)
  try{
    await ui.settle();const before=ui.calls.filter(call=>call[0]==='layout').length
    ui.button('同步最新菜單與食譜').props.onClick();await ui.settle()
    assert.equal(ui.calls.filter(call=>call[0]==='preview').length,1)
    ui.syncDialog().props.onApply([],[]);await ui.settle()
    assert.equal(ui.calls.filter(call=>call[0]==='sync').length,1)
    assert.ok(ui.calls.filter(call=>call[0]==='layout').length>before)
    assert.equal(ui.matrix().props.readOnly,false)
    assert.equal(ui.syncDialog(),undefined)
  }finally{ui.close()}
})

test('confirmed and procurement-locked sheets expose no meal entry',async()=>{
  for(const change of [{status:'confirmed'},{status:'cancelled'},{purchase_locked:true}]){
    const f=fixture();Object.assign(f.detail,change);const ui=harness(f)
    try{await ui.settle();assert.equal(ui.matrix().props.onEditMeal,undefined);assert.equal(ui.mealDialog(),undefined)}finally{ui.close()}
  }
})

test('shared controller includes optional adjustment context without changing ordinary menu save',async()=>{
  const calls=[],f=fixture(),slot={menu_date:day,menu_meal_type_id:'meal-a',menu_day_id:null,notes:null,dishes:[],slot_fingerprint:'a'.repeat(64)}
  const request=async(path,init)=>{if(init){calls.push(JSON.parse(init.body));return f.layouts['menu-a']}return path.includes('/meal-slots/')?slot:path.endsWith('/editor')?f.layouts['menu-a']:{items:[]}}
  for(const context of [undefined,{sheet_id:'sheet',lock_version:3}]){const controller=new MealEditorController('menu-a',day,'meal-a',request,context);await controller.load();await controller.save()}
  assert.equal('ordering_adjustment_context' in calls[0],false)
  assert.deepEqual(calls[1].ordering_adjustment_context,{sheet_id:'sheet',lock_version:3})
})

test('context lock errors retain meal input and require closing rather than retrying an old worksheet token',async()=>{
  for(const code of ['LOCK_VERSION_CONFLICT','SNAPSHOT_LOCKED','INVALID_ADJUSTMENT_STATUS']){
    const f=fixture(),slot={menu_date:day,menu_meal_type_id:'meal-a',menu_day_id:null,notes:null,dishes:[],slot_fingerprint:'a'.repeat(64)}
    const request=async(path,init)=>{if(init)throw {status:409,detail:{code}};return path.includes('/meal-slots/')?slot:path.endsWith('/editor')?f.layouts['menu-a']:{items:[]}}
    const controller=new MealEditorController('menu-a',day,'meal-a',request,{sheet_id:'sheet',lock_version:1})
    await controller.load();controller.change({...controller.getSnapshot().slot,notes:'保留餐次輸入'});await controller.save()
    assert.equal(controller.getSnapshot().slot.notes,'保留餐次輸入')
    assert.equal(controller.getSnapshot().contextBlocked,true)
    assert.equal(controller.getSnapshot().dirty,true)
  }
})

test('automatic permission requires exact source identities, backend safety flags and one meal scope',()=>{
  const {detail,layouts}=fixture(),preview=safePreview(detail),layout=layouts['menu-a']
  assert.equal(canAutoApplyMealSync(preview,detail,target,layout,false),true)
  assert.equal(canAutoApplyMealSync(preview,detail,target,layout,true),false)
  for(const mutate of [
    p=>p.removed_ingredients.push(riskyPreview(detail).removed_ingredients[0]),
    p=>{p.added_ingredients=[{requires_confirmation:true}];p.summary.added_ingredients=1},
    p=>{p.unit_conflicts=[{requires_confirmation:true}];p.summary.unit_conflicts=1},
    p=>{p.line_changes[0].requires_confirmation=true},
    p=>{delete p.line_changes[0].requires_confirmation},
    p=>{p.line_changes[0].preserves_adjustment=false},
    p=>{p.line_changes[0].change_types=['unknown_future_change']},
    p=>{p.line_changes[0].change_types=['menu_position_changed']},
    p=>{p.line_changes[0].current.source_dish_id='pork'},
    p=>{p.line_changes[0].current.source_ingredient_id='pork-ingredient'},
    p=>{p.line_changes[0].current.source_dish_ingredient_id='replacement-recipe'},
    p=>{p.line_changes[0].source_line_key='other'},
    p=>{p.line_changes.push(p.line_changes[0]);p.summary.changed_lines=2},
    p=>{delete p.unit_conflicts},
    p=>{p.summary.changed_lines=8},
    p=>{p.preview_source_fingerprint='z'.repeat(64)},
    p=>{p.saved_source_fingerprint='old'},
    p=>{p.lock_version++},
    p=>{p.sheet_id='other'},
    p=>{p.status='confirmed'},
  ]){
    const candidate=structuredClone(preview);mutate(candidate)
    assert.equal(canAutoApplyMealSync(candidate,detail,target,layout,false),false)
  }
  for(const changes of [{status:'confirmed'},{purchase_locked:true},{purchase_locked:undefined}])assert.equal(canAutoApplyMealSync(preview,{...detail,...changes},target,layout,false),false)
  for(const changes of [{requirement_date:'2026-09-02'},{source_meal_type_id:'other-meal'},{source_menu_id:'menu-b'}])assert.equal(canAutoApplyMealSync(preview,{...detail,lines:[{...detail.lines[0],...changes}]},target,layout,false),false)
  assert.equal(canAutoApplyMealSync(preview,detail,target,{...layout,slots:[]},false),false)
})

test('safe changed meal previews and applies exactly once, keeps manual quantity/unit and updates matrix',async()=>{
  const f=fixture();Object.assign(f.detail.lines[0],{adjusted_quantity:'5.25',adjusted_unit:'斤',effective_quantity:'5.25',effective_unit:'斤'})
  const ui=harness(f)
  try{
    await ui.settle();const layoutCalls=ui.calls.filter(c=>c[0]==='layout').length
    ui.matrix().props.onEditMeal(target);await ui.settle();await ui.saved()
    assert.deepEqual(ui.calls.filter(c=>c[0]==='preview'),[['preview','sheet',1]])
    const calls=ui.calls.filter(c=>c[0]==='sync');assert.equal(calls.length,1)
    assert.deepEqual({...calls[0][2],accepted_removed_source_line_keys:[...calls[0][2].accepted_removed_source_line_keys],reset_adjustment_line_ids:[...calls[0][2].reset_adjustment_line_ids]}, {lock_version:1,expected_source_fingerprint:'b'.repeat(64),accepted_removed_source_line_keys:[],reset_adjustment_line_ids:[]})
    assert.equal(ui.mealDialog(),undefined);assert.equal(ui.syncDialog(),undefined)
    assert.ok(ui.matrix());assert.equal(ui.matrix().props.readOnly,false)
    assert.equal(ui.matrix().props.values.line,'5.25');assert.equal(ui.matrix().props.units.line,'斤')
    assert.equal(ui.detail().lines[0].system_quantity,'3');assert.equal(ui.detail().lines[0].id,'line')
    assert.ok(ui.calls.filter(c=>c[0]==='layout').length>layoutCalls)
    assert.match(ui.texts(),/菜單與叫貨資料已更新/)
    assert.deepEqual([ui.scroll.scrollLeft,ui.scroll.scrollTop,ui.viewport.scrollY],[640,320,470])
  }finally{ui.close()}
})

test('unmodified save and ordinary close do not preview or apply',async()=>{
  const ui=harness()
  try{
    await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle()
    ui.mealDialog().props.onClose();await ui.settle()
    ui.matrix().props.onEditMeal(target);await ui.settle();await ui.saved(undefined,false)
    assert.equal(ui.calls.some(c=>c[0]==='preview'||c[0]==='sync'),false)
    assert.equal(ui.matrix().props.readOnly,false)
  }finally{ui.close()}
})

test('additions, even unadjusted removals, replacements, uncertain positions and unit conflicts open review',async()=>{
  for(const kind of ['added','removed','replacement','position','unit']){
    const ui=harness()
    try{
      const p=safePreview(ui.api.detail)
      if(kind==='removed'){ui.api.preview=riskyPreview(ui.api.detail)}
      else if(kind==='added'){p.added_ingredients=[{current:{source_line_key:'new',system_quantity:'3',system_unit:'kg'},requires_confirmation:true,preserves_adjustment:false}];p.summary.added_ingredients=1;ui.api.preview=p}
      else if(kind==='replacement'){p.possible_dish_replacements=[{previous:{dish_name:'烤雞腿'},current:{dish_name:'炸豬排'},requires_confirmation:true,preserves_adjustment:false}];p.summary.possible_dish_replacements=1;ui.api.preview=p}
      else if(kind==='position'){p.line_changes[0].change_types=['menu_position_changed'];ui.api.preview=p}
      else {p.unit_conflicts=[{previous:p.line_changes[0].previous,current:{system_unit:'包'},requires_confirmation:true,preserves_adjustment:true}];p.summary.unit_conflicts=1;ui.api.preview=p}
      await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();await ui.saved()
      assert.ok(ui.syncDialog());assert.equal(ui.calls.filter(c=>c[0]==='sync').length,0)
      assert.deepEqual(ui.syncDialog().props.preview,ui.api.preview)
      ui.syncDialog().props.onCancel();await ui.settle()
      assert.equal(ui.matrix().props.values.line,'2');assert.equal(ui.matrix().props.readOnly,true)
      assert.ok(ui.button('同步最新菜單與食譜'));assert.equal(ui.button('完成叫貨調整'),undefined)
    }finally{ui.close()}
  }
})

test('prior pending changes and changes in another meal never autoapply whole-sheet preview',async()=>{
  for(const prior of [false,true]){
    const f=fixture();f.detail.stale=prior
    if(!prior)f.detail.lines[0].requirement_date='2026-09-02'
    const ui=harness(f)
    try{await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();await ui.saved();assert.ok(ui.syncDialog());assert.equal(ui.calls.some(c=>c[0]==='sync'),false)}finally{ui.close()}
  }
})

test('preview failure preserves saved menu, quantities and pending marker with manual recovery',async()=>{
  for(const failure of ['previewFail','refreshFail']){
    const ui=harness()
    try{
      await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();ui.api[failure]=true;await ui.saved()
      assert.equal(ui.mealDialog(),undefined);assert.equal(ui.matrix().props.values.line,'2')
      assert.equal(ui.matrix().props.readOnly,true);assert.equal(ui.calls.some(c=>c[0]==='sync'),false)
      assert.match(ui.texts(),/菜單已儲存，但叫貨資料尚未同步/)
      assert.ok(ui.button('同步最新菜單與食譜'));assert.doesNotMatch(ui.texts(),/菜單與叫貨資料已更新/)
    }finally{ui.close()}
  }
})

test('apply source/version/purchase conflicts preserve inputs, stop without retry and do not report success',async()=>{
  for(const code of ['SYNC_SOURCE_CHANGED','LOCK_VERSION_CONFLICT','SNAPSHOT_LOCKED','ADJUSTMENT_DRAFT_EXISTS']){
    const ui=harness()
    try{
      await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();ui.api.syncFail=code;await ui.saved()
      assert.equal(ui.calls.filter(c=>c[0]==='sync').length,1)
      assert.equal(ui.calls.filter(c=>c[0]==='preview').length,1)
      assert.equal(ui.matrix().props.readOnly,true);assert.equal(ui.matrix().props.values.line,'2')
      assert.match(ui.texts(),/菜單已儲存，但叫貨資料尚未同步/);assert.doesNotMatch(ui.texts(),/菜單與叫貨資料已更新/)
    }finally{ui.close()}
  }
})

test('pending automatic preview blocks stale writes and duplicate callbacks before a rerender',async()=>{
  const ui=harness();let release
  try{
    await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle()
    ui.api.pendingPreview=new Promise(resolve=>{release=resolve})
    const saved=ui.mealDialog().props.onSaved,change=ui.matrix().props.onChange,edit=ui.matrix().props.onEditMeal
    ui.api.detail.stale=true
    saved(ui.api.layouts['menu-a'],{changed:true});saved(ui.api.layouts['menu-a'],{changed:true});change('line','999');edit(target)
    await ui.settle();assert.equal(ui.calls.filter(c=>c[0]==='preview').length,1);assert.equal(ui.matrix().props.values.line,'2')
    assert.equal(ui.mealDialog(),undefined);assert.ok(ui.matrix());assert.equal(ui.matrix().props.saving,true)
    release();await ui.settle();assert.equal(ui.calls.filter(c=>c[0]==='sync').length,1)
  }finally{release?.();ui.close()}
})

test('pending apply guards duplicate submission; switching/unmounting ignores late preview',async()=>{
  const ui=harness();let release
  try{
    await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle()
    ui.api.pendingSync=new Promise(resolve=>{release=resolve});await ui.saved()
    assert.equal(ui.calls.filter(c=>c[0]==='sync').length,1);assert.equal(ui.matrix().props.saving,true)
    assert.equal(ui.matrix().props.canEditMeal(target),false)
    release();await ui.settle();assert.equal(ui.matrix().props.saving,false)
  }finally{release?.();ui.close()}
  for(const leave of ['unmount','different-sheet']){
    const late=harness();let unblock
    try{
      await late.settle();late.matrix().props.onEditMeal(target);await late.settle()
      late.api.pendingPreview=new Promise(resolve=>{unblock=resolve});await late.saved()
      if(leave==='unmount')late.close();else late.setDetail({...late.detail(),id:'other-sheet'})
      unblock();await late.settle();assert.equal(late.calls.some(c=>c[0]==='sync'),false)
    }finally{unblock?.();late.close()}
  }
})

test('fresh state protection rejects confirmation or purchase lock between meal save and preview',async()=>{
  for(const change of [{status:'confirmed'},{status:'cancelled'},{purchase_locked:true}]){
    const ui=harness()
    try{
      await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();Object.assign(ui.api.detail,change);await ui.saved()
      assert.equal(ui.calls.some(c=>c[0]==='preview'||c[0]==='sync'),false)
      assert.equal(ui.matrix().props.readOnly,true)
    }finally{ui.close()}
  }
})

test('explicit review submits only user choices and prevents duplicate apply',async()=>{
  const ui=harness();let release
  try{
    await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle();ui.api.preview=riskyPreview(ui.api.detail);await ui.saved()
    ui.api.pendingSync=new Promise(resolve=>{release=resolve})
    const apply=ui.syncDialog().props.onApply
    apply(['menu-dish:recipe-line'],[]);apply(['menu-dish:recipe-line'],[]);await ui.settle()
    assert.equal(ui.calls.filter(c=>c[0]==='sync').length,1)
    assert.deepEqual([...ui.calls.find(c=>c[0]==='sync')[2].accepted_removed_source_line_keys],['menu-dish:recipe-line'])
    release();await ui.settle();assert.equal(ui.syncDialog(),undefined)
  }finally{release?.();ui.close()}
})

test('two successive changed meals each preview/apply and keep the current authoritative version',async()=>{
  const ui=harness()
  try{
    await ui.settle()
    for(let i=0;i<2;i++){
      const date=i?'2026-09-02':day
      if(i){ui.api.detail.lines[0].requirement_date=date;ui.api.layouts['menu-a'].slots[0].menu_date=date;ui.setDetail(structuredClone(ui.api.detail));await ui.settle()}
      ui.matrix().props.onEditMeal({...target,date});await ui.settle();await ui.saved()
    }
    assert.deepEqual(ui.calls.filter(c=>c[0]==='preview').map(c=>c[2]),[1,2])
    assert.equal(ui.calls.filter(c=>c[0]==='sync').length,2)
    assert.equal(ui.matrix().props.readOnly,false);assert.equal(ui.detail().lock_version,3)
  }finally{ui.close()}
})

test('scroll restoration preserves page and internal axes and tolerates no mounted matrix',()=>{
  const matrix={scrollLeft:125,scrollTop:42},viewport={scrollX:0,scrollY:900,scrollTo(x,y){this.scrollX=x;this.scrollY=y}},root={querySelector:()=>matrix}
  const position=captureAdjustmentScroll(root,viewport)
  matrix.scrollLeft=0;matrix.scrollTop=0;viewport.scrollY=0
  restoreAdjustmentScroll(root,position,viewport)
  assert.deepEqual([matrix.scrollLeft,matrix.scrollTop,viewport.scrollY],[125,42,900])
  assert.equal(captureAdjustmentScroll(null,viewport),null)
  assert.doesNotThrow(()=>restoreAdjustmentScroll(null,position,viewport))
})

test('preview/local version mismatch never submits and no-change preview does not issue a redundant apply',async()=>{
  for(const kind of ['mismatch','no-change','local-version']){
    const ui=harness();let release
    try{
      await ui.settle();ui.matrix().props.onEditMeal(target);await ui.settle()
      if(kind==='local-version'){
        ui.api.pendingPreview=new Promise(resolve=>{release=resolve});await ui.saved()
        ui.setDetail({...ui.detail(),lock_version:2});release();await ui.settle()
      }else{
        const preview=safePreview(ui.api.detail)
        if(kind==='mismatch')preview.sheet_id='other-sheet'
        else {preview.changed=false;preview.preview_source_fingerprint=preview.saved_source_fingerprint;preview.line_changes=[];preview.summary.changed_lines=0}
        ui.api.preview=preview
        // No ingredient impact (e.g. meal notes) still previews after a real save.
        if(kind==='no-change'){
          const saved=ui.mealDialog().props.onSaved
          saved(ui.api.layouts['menu-a'],{changed:true});await ui.settle()
        }else await ui.saved()
      }
      assert.equal(ui.calls.some(c=>c[0]==='sync'),false)
      if(kind==='no-change'){assert.equal(ui.matrix().props.readOnly,false);assert.equal(ui.syncDialog(),undefined)}
      else assert.match(ui.texts(),/版本|預覽/)
    }finally{release?.();ui.close()}
  }
})

// Render the real review dialog as well: choices must start empty and cannot
// enter the request until explicitly checked by the user.
test('real review dialog keeps removal and unit-reset checkboxes opt-in and gates apply',()=>{
  const preview=riskyPreview(),snapshot=preview.removed_ingredients[0].previous
  preview.unit_conflicts=[{previous:snapshot,current:{...snapshot,system_unit:'包'},change_types:['unit_conflict'],requires_confirmation:true,preserves_adjustment:true}]
  preview.summary.unit_conflicts=1
  let cursor=0,states=[],tree,component;const applied=[]
  const jsx=(type,props)=>({type,props:props??{}}),exports={}
  const render=()=>{cursor=0;tree=component({preview,busy:false,onCancel(){},onApply:(removed,resets)=>applied.push([removed,resets])})}
  const react={useState:initial=>{const i=cursor++;states[i]??=initial;return[states[i],next=>{states[i]=typeof next==='function'?next(states[i]):next;render()}]}}
  const source=readFileSync(new URL('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx',import.meta.url),'utf8')+'\nexport {SyncAdjustmentDialog}'
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:path=>path==='react'?react:path==='react/jsx-runtime'?{jsx,jsxs:jsx}:path==='./view'?view:{}})
  component=exports.SyncAdjustmentDialog;render()
  const nodes=value=>Array.isArray(value)?value.flatMap(nodes):value&&typeof value==='object'?[value,...nodes(value.props.children)]:[]
  const inputs=()=>nodes(tree).filter(n=>n.type==='input')
  const apply=()=>nodes(tree).filter(n=>n.type==='button').at(-1)
  assert.deepEqual(inputs().map(n=>n.props.checked),[false,false]);assert.equal(apply().props.disabled,true)
  inputs()[0].props.onChange();assert.equal(apply().props.disabled,true)
  inputs()[1].props.onChange();assert.equal(apply().props.disabled,false)
  apply().props.onClick()
  assert.deepEqual(applied.map(([removed,resets])=>[[...removed],[...resets]]),[[['menu-dish:recipe-line'],['line']]])
})
