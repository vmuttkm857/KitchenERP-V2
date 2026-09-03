import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {mealGridRows} from '../src/features/menus/menuGridRows.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const grid=read('../src/features/menus/MenuWeekGrid.tsx')
const editor=read('../src/features/menus/MenuEditor.tsx')
const panel=read('../src/features/menus/MenuEditorPanel.tsx')
const dialog=read('../src/features/menus/MenuColumnDialog.tsx')
const model=read('../../backend/app/domains/menus/models.py')

const meal={id:'custom-meal',menu_id:'menu',name:'董事長宵夜',sort_order:1,is_active:true}
const dates=['2026-09-07','2026-09-08','2026-09-09']
const dish=(name,order)=>({dish_id:name,dish_name:name,diner_count:100,notes:null,sort_order:order})
function rows(columns,dishesByDate){return mealGridRows(dates,meal,columns,(date)=>({menu_date:date,menu_meal_type_id:meal.id,notes:null,dishes:dishesByDate[date]??[]}))}

test('grid places 菜單欄位 between meal and dates and keeps separate click targets',()=>{
  assert.match(grid,/餐別<\/th><th className="menu-column-heading">菜單欄位<\/th>/)
  assert.match(grid,/onEditColumns\(meal\)/)
  assert.match(grid,/onSelect\(date, meal\)/)
})

test('labels sort independently and extra labels keep empty dish cells',()=>{
  const result=rows([{id:'b',menu_meal_type_id:meal.id,name:'青菜',sort_order:2},{id:'a',menu_meal_type_id:meal.id,name:'主菜',sort_order:1}],{'2026-09-07':[dish('菜A',1)]})
  assert.deepEqual(result.map(row=>row.label),['主菜','青菜'])
  assert.equal(result[1].dishes[0],null)
})

test('extra and uneven daily dishes remain visible with blank labels',()=>{
  const result=rows([{id:'a',menu_meal_type_id:meal.id,name:'主菜',sort_order:1}],{
    '2026-09-07':[dish('菜A',1),dish('菜B',2),dish('菜C',3)],'2026-09-08':[dish('菜D',1),dish('菜E',2)],
  })
  assert.equal(result.length,3);assert.deepEqual(result.map(row=>row.label),['主菜','',''])
  assert.equal(result[2].dishes[0]?.dish_name,'菜C');assert.equal(result[2].dishes[1],null)
})

test('empty custom meal remains clickable and dialog supports free CRUD and reorder',()=>{
  assert.equal(rows([],{}).length,1)
  for(const token of ['自由輸入欄位名稱','新增','儲存','上移','下移','刪除'])assert.match(dialog,new RegExp(token))
  assert.match(editor,/columns=\{data\.meal_type_columns\}/)
})

test('meal editor stays unchanged and model has no dish-column mapping',()=>{
  assert.match(panel,/已排菜色/);assert.match(panel,/DishSearchPicker/);assert.match(panel,/儲存本餐/)
  assert.doesNotMatch(panel,/菜單欄位|column selector|column_id/)
  const menuDish=model.slice(model.indexOf('class MenuDish'))
  assert.doesNotMatch(menuDish,/menu_column|column_id|meal_type_column/)
})
