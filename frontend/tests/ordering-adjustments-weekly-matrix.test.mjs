import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {buildAdjustmentMenuMatrix} from '../src/features/order_adjustments/matrix.ts'
import {editableDecimalString} from '../src/features/order_adjustments/editor.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const page=read('../src/features/order_adjustments/OrderingAdjustmentsPage.tsx')
const css=read('../src/styles/global.css')
const menu={menu_id:'menu-a',menu_name:'普通伙',start_date:'2026-09-28',end_date:'2026-10-04',is_active:true}
const criteria={menu_ids:['menu-a'],start_date:'2026-09-28',end_date:'2026-10-04'}
const layout={menu:{id:'menu-a',name:'普通伙',start_date:menu.start_date,end_date:menu.end_date,category_id:null,category_name:null,notes:null,is_active:true},dates:[],meal_types:[{id:'lunch',menu_id:'menu-a',name:'午餐',sort_order:2,is_active:true},{id:'breakfast',menu_id:'menu-a',name:'早餐',sort_order:1,is_active:true}],meal_type_columns:[{id:'main',menu_meal_type_id:'breakfast',name:'主菜',sort_order:1},{id:'side',menu_meal_type_id:'breakfast',name:'青菜',sort_order:2}],slots:[]}
const line=(overrides={})=>({id:'line-a',snapshot_item_id:'snapshot',source_line_key:'key',source_menu_id:'menu-a',menu_name_snapshot:'普通伙',source_menu_day_id:'day-a',requirement_date:'2026-09-28',source_meal_type_id:'breakfast',meal_type_name_snapshot:'早餐',meal_type_sort_order_snapshot:1,source_menu_meal_type_column_id:'main',menu_meal_type_column_sort_order_snapshot:1,source_menu_dish_id:'menu-dish-a',menu_dish_sort_order_snapshot:1,source_dish_id:'dish-a',dish_code_snapshot:'01',dish_name_snapshot:'滷肉',diner_count_snapshot:30,source_dish_ingredient_id:'dish-ingredient-a',dish_ingredient_sort_order_snapshot:1,source_ingredient_id:'ingredient-a',ingredient_code_snapshot:'I01',ingredient_name_snapshot:'豬肉',source_supplier_id:null,supplier_name_snapshot:null,quantity_per_person_snapshot:'1',loss_rate_snapshot:'0',recipe_unit_snapshot:'g',system_quantity:'1.500000',system_unit:'kg',adjusted_quantity:null,effective_quantity:'1.500000',modified:false,stale:false,stale_reasons:[],...overrides})

test('weekly matrix keeps seven date columns and meal and column ordering',()=>{
  const matrix=buildAdjustmentMenuMatrix([line()],menu,layout,criteria)
  assert.deepEqual(matrix.dates,['2026-09-28','2026-09-29','2026-09-30','2026-10-01','2026-10-02','2026-10-03','2026-10-04'])
  assert.deepEqual(matrix.meals.map(meal=>meal.name),['早餐','午餐'])
  assert.deepEqual(matrix.meals[0].rows.map(row=>row.label),['主菜','青菜'])
  assert.equal(matrix.meals[0].rows[0].cells['2026-09-28'][0].name,'滷肉')
  assert.deepEqual(matrix.meals[0].rows[1].cells,{})
})

test('same ingredient remains independently editable across dishes and dates',()=>{
  const lines=[line(),line({id:'line-b',source_line_key:'key-b',source_menu_day_id:'day-b',requirement_date:'2026-09-29',source_menu_dish_id:'menu-dish-b',source_dish_id:'dish-b',dish_name_snapshot:'白菜滷',source_dish_ingredient_id:'dish-ingredient-b',menu_dish_sort_order_snapshot:2})]
  const matrix=buildAdjustmentMenuMatrix(lines,menu,layout,criteria)
  assert.equal(matrix.meals[0].rows[0].cells['2026-09-28'][0].lines[0].id,'line-a')
  assert.equal(matrix.meals[0].rows[0].cells['2026-09-29'][0].lines[0].id,'line-b')
})

test('multiple dishes in one visual cell remain ordered and are never aggregated',()=>{
  const lines=[line({id:'line-b',source_line_key:'key-b',source_menu_dish_id:'menu-dish-b',source_dish_id:'dish-b',dish_name_snapshot:'第二道',source_dish_ingredient_id:'dish-ingredient-b',menu_dish_sort_order_snapshot:2}),line({dish_name_snapshot:'第一道',menu_dish_sort_order_snapshot:1})]
  const dishes=buildAdjustmentMenuMatrix(lines,menu,layout,criteria).meals[0].rows[0].cells['2026-09-28']
  assert.deepEqual(dishes.map(dish=>dish.name),['第一道','第二道'])
  assert.equal(dishes.length,2)
})

test('unassigned dishes fill free rows then append unnamed overflow without hiding dishes',()=>{
  const lines=[line({source_menu_meal_type_column_id:'main'}),line({id:'line-b',source_line_key:'key-b',source_menu_dish_id:'menu-dish-b',source_dish_id:'dish-b',dish_name_snapshot:'未指定一',source_dish_ingredient_id:'dish-ingredient-b',source_menu_meal_type_column_id:null,menu_dish_sort_order_snapshot:2}),line({id:'line-c',source_line_key:'key-c',source_menu_dish_id:'menu-dish-c',source_dish_id:'dish-c',dish_name_snapshot:'未指定二',source_dish_ingredient_id:'dish-ingredient-c',source_menu_meal_type_column_id:null,menu_dish_sort_order_snapshot:3})]
  const rows=buildAdjustmentMenuMatrix(lines,menu,layout,criteria).meals[0].rows
  assert.equal(rows[1].cells['2026-09-28'][0].name,'未指定一')
  assert.equal(rows[2].label,'')
  assert.equal(rows[2].cells['2026-09-28'][0].name,'未指定二')
})

test('friendly decimal display is string-safe and tabs share one unsaved values state',()=>{
  assert.equal(editableDecimalString('1.500000'),'1.5')
  assert.equal(editableDecimalString('1800.000000'),'1800')
  assert.equal(editableDecimalString('0.000001'),'0.000001')
  assert.match(page,/const \[values,setValues\]=useState/)
  assert.match(page,/menuDirtyCounts/)
  assert.match(page,/setActiveMenuId\(matrix\.menuId\)/)
  assert.doesNotMatch(page,/ingredient_code_snapshot/)
})

test('editable and read-only states share the same matrix and only editable mode renders inputs',()=>{
  assert.match(page,/<AdjustmentWeeklyMatrix matrix=\{activeMatrix\}/)
  assert.match(page,/readOnly\?<b>\{formatAdjustmentQuantity\(line\.effective_quantity\)\}<\/b>:<input/)
  assert.match(page,/showRestore=!decimalStringsEqual\(actual,line\.system_quantity\)\|\|dirty/)
  assert.match(css,/\.ordering-adjustment-matrix/)
  assert.match(css,/\.ordering-adjustment-matrix \.matrix-column-cell\{position:sticky/)
  assert.match(css,/\.ordering-adjustment-savebar\{position:sticky/)
})
