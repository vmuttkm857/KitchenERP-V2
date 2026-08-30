import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { activeCategoryOptions,editableCategoryOptions,loadIngredientCandidates } from '../src/features/ingredients/ingredientCandidates.ts'
import { buildListQuery } from '../src/utils/listQuery.ts'

const categories=[
  {id:'active-1',name:'肉類',is_active:true},
  {id:'inactive-current',name:'舊分類',is_active:false},
  {id:'inactive-other',name:'其他停用分類',is_active:false},
]

test('CategoryList response items populate create selector and list filter candidates',async()=>{
  const result=await loadIngredientCandidates(async()=>({items:categories,pagination:{page:1,page_size:100,total:3}}),async()=>({items:[]}))
  assert.deepEqual(result.categories,categories)
  assert.deepEqual(activeCategoryOptions(result.categories??[]).map(item=>item.id),['active-1'])
})

test('edit selector preserves its current inactive category and labels can use is_active',()=>{
  assert.deepEqual(editableCategoryOptions(categories,'inactive-current').map(item=>item.id),['active-1','inactive-current'])
  assert.equal(editableCategoryOptions(categories,'missing').some(item=>!item.is_active),false)
})

test('supplier failure cannot discard a successful Category response',async()=>{
  const result=await loadIngredientCandidates(async()=>({items:categories}),async()=>{throw new Error('supplier failed')})
  assert.deepEqual(result.categories,categories)
  assert.equal(result.categoryFailed,false)
  assert.equal(result.supplierFailed,true)
})

test('Category API failure is explicit while supplier candidates can still load',async()=>{
  const result=await loadIngredientCandidates(async()=>{throw new Error('category failed')},async()=>({items:[{id:'supplier-1',name:'供應商',is_active:true}]}))
  assert.equal(result.categories,null)
  assert.equal(result.categoryFailed,true)
  assert.deepEqual(result.suppliers?.map(item=>item.id),['supplier-1'])
  const page=readFileSync(new URL('../src/features/ingredients/IngredientsPage.tsx',import.meta.url),'utf8')
  assert.match(page,/分類載入失敗，請稍後再試。/)
  assert.match(page,/categoryOptionsError&&<Feedback type="error">/)
})

test('category selection remains a server-side Ingredient query with pagination and search',()=>{
  const query=new URLSearchParams(buildListQuery({page:2,pageSize:50,search:'雞肉',active:'true',categoryId:'active-1'}))
  assert.deepEqual(Object.fromEntries(query),{page:'2',page_size:'50',search:'雞肉',active:'true',category_id:'active-1'})
})
