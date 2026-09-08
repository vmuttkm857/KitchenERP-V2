import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {mealGridRows} from '../src/features/menus/menuGridRows.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const grid=read('../src/features/menus/MenuWeekGrid.tsx')
const editor=read('../src/features/menus/MenuEditor.tsx')
const panel=read('../src/features/menus/MenuEditorPanel.tsx')
const dialog=read('../src/features/menus/MenuColumnDialog.tsx')

const meal={id:'custom-meal',menu_id:'menu',name:'董事長宵夜',sort_order:1,is_active:true}
const otherMeal={id:'other-meal',menu_id:'menu',name:'早餐',sort_order:2,is_active:true}
const dates=['2026-09-07','2026-09-08','2026-09-09']
const columns=[
  {id:'main-1',menu_meal_type_id:meal.id,name:'主菜1',sort_order:1},
  {id:'main-2',menu_meal_type_id:meal.id,name:'主菜2',sort_order:2},
  {id:'veg-1',menu_meal_type_id:meal.id,name:'青菜1',sort_order:3},
  {id:'veg-2',menu_meal_type_id:meal.id,name:'青菜2',sort_order:4},
  {id:'side-1',menu_meal_type_id:meal.id,name:'備菜1',sort_order:5},
  {id:'soup',menu_meal_type_id:meal.id,name:'湯',sort_order:6},
]
const dish=(name,order,columnId=null)=>({dish_id:name,dish_name:name,menu_meal_type_column_id:columnId,diner_count:100,notes:null,sort_order:order})
function rows(mealColumns,dishesByDate){return mealGridRows(dates,meal,mealColumns,(date)=>({menu_date:date,menu_meal_type_id:meal.id,notes:null,dishes:dishesByDate[date]??[]}))}

test('grid keeps 菜單欄位 between meal and dates and separate click targets',()=>{
  assert.match(grid,/餐別<\/th><th className="menu-column-heading">菜單欄位<\/th>/)
  assert.match(grid,/onEditColumns\(meal\)/)
  assert.match(grid,/onSelect\(date, meal\)/)
})

test('all-null legacy dishes keep sort order and overflow remains visible',()=>{
  const result=rows(columns.slice(0,2),{'2026-09-07':[dish('菜C',3),dish('菜A',1),dish('菜B',2)]})
  assert.deepEqual(result.map(row=>row.label),['主菜1','主菜2',''])
  assert.deepEqual(result.map(row=>row.dishes[0]?.dish_name??null),['菜A','菜B','菜C'])
})

test('assigned dish stays in its column and empty configured rows remain blank',()=>{
  const result=rows(columns,{'2026-09-07':[dish('蘿蔔湯',1,'soup')]})
  assert.equal(result.length,6)
  assert.equal(result[5].label,'湯')
  assert.equal(result[5].dishes[0]?.dish_name,'蘿蔔湯')
  assert.equal(result[0].dishes[0],null)
})

test('assigned and fallback dishes mix without overwriting assigned rows',()=>{
  const result=rows(columns,{'2026-09-07':[
    dish('A',1,'main-1'),dish('B',2),dish('C',3),dish('D',4,'soup'),
  ]})
  assert.deepEqual(result.map(row=>row.dishes[0]?.dish_name??null),['A','B','C',null,null,'D'])
})

test('unknown or duplicate assignments fall back safely and never hide dishes',()=>{
  const result=rows(columns.slice(0,2),{'2026-09-07':[
    dish('A',1,'main-1'),dish('B',2,'main-1'),dish('C',3,'missing-column'),dish('D',4),
  ]})
  assert.deepEqual(result.map(row=>row.dishes[0]?.dish_name??null),['A','B','C','D'])
})

test('same column aligns horizontally across dates despite different dish order',()=>{
  const result=rows(columns,{
    '2026-09-07':[dish('星期一湯',1,'soup'),dish('星期一主菜',2,'main-1')],
    '2026-09-08':[dish('星期二主菜',1,'main-1'),dish('星期二湯',2,'soup')],
  })
  assert.equal(result[0].dishes[0]?.dish_name,'星期一主菜')
  assert.equal(result[0].dishes[1]?.dish_name,'星期二主菜')
  assert.equal(result[5].dishes[0]?.dish_name,'星期一湯')
  assert.equal(result[5].dishes[1]?.dish_name,'星期二湯')
})

test('editor payload preserves column id and new dishes default to null',()=>{
  assert.match(editor,/menu_meal_type_column_id:\s*null/)
  assert.match(editor,/\{ id, dish_id, menu_meal_type_column_id, diner_count, notes, sort_order \}/)
  assert.match(editor,/\{ id, dish_id, menu_meal_type_column_id, diner_count, notes, sort_order \}/)
  assert.match(editor,/dishIndex === index \? \{ \.\.\.dish, \.\.\.changes \} : dish/)
  assert.match(editor,/\{ \.\.\.dish, sort_order: order \+ 1 \}/)
})

test('selector uses only current meal columns and prevents duplicate selection',()=>{
  assert.match(panel,/filter\(column=>column\.menu_meal_type_id===meal\.id\)/)
  assert.match(panel,/sort\(\(a,b\)=>a\.sort_order-b\.sort_order/)
  assert.match(panel,/>菜單欄位<select/)
  assert.match(panel,/<option value="">未指定<\/option>/)
  assert.match(panel,/disabled=\{usedColumnIds\.has\(column\.id\)&&dish\.menu_meal_type_column_id!==column\.id\}/)
  assert.match(editor,/columns=\{data\.meal_type_columns\}/)
  assert.ok(otherMeal.id)
})

test('existing meal editor and column management flows remain available',()=>{
  for(const token of ['已排菜色','DishSearchPicker','儲存本餐','人數','菜色備註','上移','下移'])assert.match(panel,new RegExp(token))
  for(const token of ['自由輸入欄位名稱','新增','儲存','上移','下移','刪除'])assert.match(dialog,new RegExp(token))
})
