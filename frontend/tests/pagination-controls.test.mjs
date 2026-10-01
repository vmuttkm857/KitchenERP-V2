import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

import {jumpPage,paginationItems} from '../src/components/ui/pagination.ts'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const component=read('../src/components/ui/PaginationControls.tsx')
const ingredients=read('../src/features/ingredients/IngredientsPage.tsx')
const dishes=read('../src/features/dishes/DishesPage.tsx')

test('pagination window covers one first middle and final pages with ellipses',()=>{
  assert.deepEqual(paginationItems(1,1),[1])
  assert.deepEqual(paginationItems(1,27),[1,2,3,4,5,'ellipsis',27])
  assert.deepEqual(paginationItems(15,27),[1,'ellipsis',13,14,15,16,17,'ellipsis',27])
  assert.deepEqual(paginationItems(26,27),[1,'ellipsis',23,24,25,26,27])
})

test('jump validation accepts only an in-range integer',()=>{
  assert.equal(jumpPage('18',27),18)
  for(const value of ['0','-1','28','abc','1.5',''])assert.equal(jumpPage(value,27),null)
})

test('shared controls expose first previous active next last and jump actions',()=>{
  for(const token of ['第一頁','上一頁','aria-current','下一頁','最後一頁','跳至頁碼','前往'])assert.match(component,new RegExp(token))
  assert.match(component,/paginationItems\(page,pages\)/)
  assert.match(component,/請輸入 1～\{pages\} 的整數頁碼/)
})

test('ingredient and dish lists both use shared pagination and keep pages legal after totals shrink',()=>{
  assert.match(ingredients,/PaginationControls/)
  assert.match(dishes,/PaginationControls/)
  assert.match(ingredients,/availablePage=validPage\(page,ingredients\.pagination\.total,pageSize\)/)
  assert.match(dishes,/availablePage=validPage\(page,dishes\.pagination\.total,pageSize\)/)
  for(const source of [ingredients,dishes]){
    assert.match(source,/page:1|setPage\(1\)/)
  }
})
