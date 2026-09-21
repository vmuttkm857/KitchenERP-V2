import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

import {mealSectionTone} from '../src/features/menus/mealSectionTone.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const grid=read('../src/features/menus/MenuWeekGrid.tsx')
const css=read('../src/styles/global.css')

test('dynamic meal sections use display index instead of meal names',()=>{
  const dynamicMeals=['早餐','早點','午餐','午點','晚餐','晚點二','特殊餐']
  assert.deepEqual(dynamicMeals.map((_,index)=>mealSectionTone(index)),[
    'menu-meal-tone-0','menu-meal-tone-1','menu-meal-tone-2',
    'menu-meal-tone-3','menu-meal-tone-4','menu-meal-tone-5','menu-meal-tone-0',
  ])
  assert.match(grid,/meals\.flatMap\(\(meal,mealIndex\)/)
  assert.match(grid,/data-meal-id=\{meal\.id\}/)
  assert.match(grid,/\{meal\.name\}/)
  assert.doesNotMatch(grid,/meal\.name\s*===/)
})

test('meal sections expose compact start end and sticky-name styling',()=>{
  assert.match(grid,/menu-meal-row-start/)
  assert.match(grid,/menu-meal-row-end/)
  assert.match(grid,/sticky-col meal-name-cell/)
  for(let index=0;index<6;index++)assert.match(css,new RegExp(`\\.menu-meal-tone-${index}`))
  assert.match(css,/\.menu-meal-row-start>th/)
  assert.match(css,/\.menu-meal-row-end>th/)
  assert.match(css,/\.meal-name-cell/)
})

test('drag and click handlers remain on the existing grid cells',()=>{
  assert.match(grid,/onDragStart/)
  assert.match(grid,/onDragOver/)
  assert.match(grid,/onDrop/)
  assert.match(grid,/onMoveDish\(sourceId,target\)/)
  assert.match(grid,/onSelect\(date, meal\)/)
})
