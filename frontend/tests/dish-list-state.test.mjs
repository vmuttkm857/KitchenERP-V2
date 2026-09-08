import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

import {validPage} from '../src/utils/listQuery.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/app/App.tsx')
const dishes=read('../src/features/dishes/DishesPage.tsx')

test('dish list state lives above recipe and production subpages',()=>{
  assert.match(app,/useState<DishListState>\(initialDishListState\)/)
  assert.match(app,/<DishesPage listState=\{dishListState\} onListStateChange=\{setDishListState\}/)
  assert.match(app,/RecipeEditor dish=\{recipeDish\} onClose=\{\(\)=>navigate\('dishes'\)\}/)
  assert.match(app,/ProductionProfilePage dish=\{productionDish\}[^>]+onClose=\{\(\)=>navigate\('dishes'\)\}/)
})

test('all existing dish-list controls use the preserved state',()=>{
  for(const field of ['search','categoryFilter','activeFilter','page','pageSize','showNutrition']){
    assert.match(dishes,new RegExp(`${field}:`))
  }
  assert.match(dishes,/search:event\.target\.value,page:1/)
  assert.match(dishes,/categoryFilter:event\.target\.value,page:1/)
  assert.match(dishes,/activeFilter:event\.target\.value,page:1/)
  assert.match(dishes,/pageSize:size,page:1/)
})

test('an out-of-range page falls back to the final valid page',()=>{
  assert.equal(validPage(2,25,25),1)
  assert.equal(validPage(4,51,25),3)
  assert.equal(validPage(2,0,25),1)
  assert.match(dishes,/availablePage=validPage\(page,dishes\.pagination\.total,pageSize\)/)
  assert.match(dishes,/availablePage!==page/)
})
