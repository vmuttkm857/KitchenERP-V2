import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {
  canInsertMenuDish,
  menuDishMovePayload,
  menuSlotsVisuallyEquivalent,
  mergeAuthoritativeSlotMetadata,
  optimisticallyInsertMenuDish,
} from '../src/features/menus/menuDrag.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const grid=read('../src/features/menus/MenuWeekGrid.tsx')
const editor=read('../src/features/menus/MenuEditor.tsx')
const css=read('../src/styles/global.css')
const columns=[
  {id:'main',menu_meal_type_id:'breakfast',name:'主菜',sort_order:1},
  {id:'side',menu_meal_type_id:'breakfast',name:'配菜',sort_order:2},
  {id:'soup',menu_meal_type_id:'breakfast',name:'湯',sort_order:3},
]
const dish=(id,count,order,column=null)=>({id,dish_id:`dish-${id}`,menu_meal_type_column_id:column,dish_code:id,dish_name:id,dish_category_name:null,diner_count:count,notes:`note-${id}`,sort_order:order})
const slots={
  '2026-09-01:breakfast':{menu_date:'2026-09-01',menu_meal_type_id:'breakfast',notes:null,dishes:[dish('A',300,1,'main')]},
  '2026-09-02:breakfast':{menu_date:'2026-09-02',menu_meal_type_id:'breakfast',notes:null,dishes:[dish('B',10,1,'main'),dish('C',20,2,'side'),dish('D',30,3,'soup')]},
}

test('insert metadata maps to the dedicated move API without swap semantics',()=>{
  const target={targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:1,beforeMenuDishId:'B',afterMenuDishId:'C'}
  assert.equal(canInsertMenuDish('A',target),true)
  assert.deepEqual(menuDishMovePayload('A',target),{
    source_menu_dish_id:'A',target_date:'2026-09-02',target_meal_type_id:'breakfast',insert_index:1,
    before_menu_dish_id:'B',after_menu_dish_id:'C',
  })
  assert.equal(canInsertMenuDish(null,target),false)
  assert.equal(canInsertMenuDish('A',target,true),false)
})

test('optimistic cross-date insertion moves the whole dish and never overwrites target dishes',()=>{
  const result=optimisticallyInsertMenuDish(slots,columns,'A',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:1,beforeMenuDishId:'B',afterMenuDishId:'C',
  })
  assert.ok(result)
  assert.deepEqual(result['2026-09-01:breakfast'].dishes,[])
  assert.deepEqual(result['2026-09-02:breakfast'].dishes.map(item=>item.id),['B','A','C','D'])
  assert.deepEqual(result['2026-09-02:breakfast'].dishes.map(item=>item.sort_order),[1,2,3,4])
  assert.equal(result['2026-09-02:breakfast'].dishes[1].diner_count,300)
  assert.equal(result['2026-09-02:breakfast'].dishes[1].notes,'note-A')
})

test('optimistic insertion supports first last and same-day reorder',()=>{
  const first=optimisticallyInsertMenuDish(slots,columns,'D',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:0,beforeMenuDishId:null,afterMenuDishId:'B',
  })
  assert.deepEqual(first['2026-09-02:breakfast'].dishes.map(item=>item.id),['D','B','C'])
  const last=optimisticallyInsertMenuDish(first,columns,'D',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:3,beforeMenuDishId:'C',afterMenuDishId:null,
  })
  assert.deepEqual(last['2026-09-02:breakfast'].dishes.map(item=>item.id),['B','C','D'])
})

test('duplicate dish at destination is rejected before optimistic mutation',()=>{
  const duplicate={...slots,'2026-09-02:breakfast':{...slots['2026-09-02:breakfast'],dishes:[dish('X',1,1,'main')]}}
  duplicate['2026-09-02:breakfast'].dishes[0].dish_id='dish-A'
  assert.equal(optimisticallyInsertMenuDish(duplicate,columns,'A',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:0,beforeMenuDishId:null,afterMenuDishId:'X',
  }),null)
})

test('equivalent authoritative response preserves optimistic visual state references',()=>{
  const optimistic=optimisticallyInsertMenuDish(slots,columns,'A',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:1,beforeMenuDishId:'B',afterMenuDishId:'C',
  })
  assert.ok(optimistic)
  const authoritative=Object.values(optimistic).map(slot=>({
    ...slot,
    menu_day_id:slot.menu_date==='2026-09-02'?'server-day-2':slot.menu_day_id,
  }))
  assert.equal(menuSlotsVisuallyEquivalent(optimistic,authoritative),true)

  const merged=mergeAuthoritativeSlotMetadata(optimistic,authoritative)
  assert.notEqual(merged,optimistic)
  assert.equal(merged['2026-09-02:breakfast'].menu_day_id,'server-day-2')
  assert.equal(merged['2026-09-02:breakfast'].dishes,optimistic['2026-09-02:breakfast'].dishes)
  assert.equal(merged['2026-09-01:breakfast'],optimistic['2026-09-01:breakfast'])
  assert.equal(mergeAuthoritativeSlotMetadata(merged,authoritative),merged)
})

test('visually different authoritative response is detected for full reconciliation',()=>{
  const optimistic=optimisticallyInsertMenuDish(slots,columns,'A',{
    targetDate:'2026-09-02',targetMealTypeId:'breakfast',insertIndex:1,beforeMenuDishId:'B',afterMenuDishId:'C',
  })
  assert.ok(optimistic)
  const authoritative=Object.values(optimistic).map(slot=>
    slot.menu_date==='2026-09-02'
      ? {...slot,dishes:slot.dishes.map(item=>item.id==='A'?{...item,diner_count:999}:item)}
      : slot,
  )
  assert.equal(menuSlotsVisuallyEquivalent(optimistic,authoritative),false)
})

test('grid uses before-after insertion lines and preserves direct click editing',()=>{
  assert.match(grid,/getBoundingClientRect\(\)/)
  assert.match(grid,/insertIndex/)
  assert.match(grid,/is-insert-before/)
  assert.match(grid,/is-insert-after/)
  assert.match(css,/height:4px/)
  assert.match(grid,/dataTransfer\.setData\('text\/plain',menuDishId\)/)
  assert.match(grid,/void onMoveDish\(sourceId,target\)/)
  assert.match(grid,/requestAnimationFrame/)
  assert.match(grid,/scheduleFinishDrag\(\)/)
  assert.match(grid,/onSelect\(date, meal\)/)
  assert.doesNotMatch(grid+editor,/confirm\s*\(/)
})

test('pending move keeps the grid mounted and failure reloads authoritative state',()=>{
  assert.match(editor,/setSlots\(optimistic\)/)
  assert.match(editor,/setMovingDish\(true\)/)
  assert.match(editor,/\/dish-move/)
  assert.match(editor,/menuSlotsVisuallyEquivalent\(optimistic,aggregate\.slots\)/)
  assert.match(editor,/mergeAuthoritativeSlotMetadata\(current,aggregate\.slots\)/)
  assert.match(editor,/else\s+applyAggregate\(aggregate\)/)
  assert.match(editor,/applyAggregate\(await apiRequest<MenuAggregate>\(`\/menus\/\$\{menu\.id\}\/editor`\)\)/)
  assert.match(editor,/菜色移動失敗，已重新載入目前菜單/)
  assert.doesNotMatch(editor,/movingDish\s*\?\s*<LoadingState/)
})
