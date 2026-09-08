import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/RestrictionGroupsPage.tsx',import.meta.url),'utf8')
const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const selectionSource=readFileSync(new URL('../src/features/postpartum/restrictionTypes.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(selectionSource,{compilerOptions:{module:ts.ModuleKind.ES2022}}).outputText
const selection=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('postpartum restriction navigation and create/edit modals are wired independently',()=>{
  assert.match(app,/postpartum-restrictions/)
  assert.match(app,/禁忌群組管理/)
  assert.match(app,/RestrictionGroupsPage/)
  assert.match(page,/creating,setCreating/)
  assert.match(page,/editingId,setEditingId/)
  assert.match(page,/key="create" groupId=\{null\}/)
  assert.match(page,/key=\{editingId\} groupId=\{editingId\}/)
  assert.match(page,/新增禁忌群組/)
  assert.match(page,/編輯禁忌群組/)
})

test('ingredient and dish selectors use active paginated server search and API categories',()=>{
  assert.match(page,/pageSize:20/)
  assert.match(page,/active:'true'/)
  assert.match(page,/categoryId/)
  assert.match(page,/useDebouncedValue\(search\)/)
  assert.match(page,/useEffect\(\(\)=>setPage\(1\),\[debounced,categoryId\]\)/)
  assert.match(page,/RequestSequence/)
  assert.match(page,/\/categories\/ingredient\?active=true&page_size=100/)
  assert.match(page,/\/categories\/dish\?active=true&page_size=100/)
  assert.match(page,/PaginationControls page=\{page\} pageSize=\{20\}/)
  for(const hardcoded of ['豬肉','雞肉','魚肉','蔬菜'])assert.doesNotMatch(page,new RegExp(hardcoded))
})

test('selection map persists independently from search category and page',()=>{
  const beef={id:'i-1',code:'01',name:'牛腱',is_active:true}
  const stock={id:'i-2',code:'02',name:'牛高湯',is_active:true}
  let selected=selection.targetMap([])
  selected=selection.toggleTarget(selected,beef)
  selected=selection.toggleTarget(selected,stock)
  assert.deepEqual([...selected.keys()],['i-1','i-2'])
  const removed=selection.toggleTarget(selected,beef)
  assert.deepEqual([...removed.keys()],['i-2'])
  assert.deepEqual([...selected.keys()],['i-1','i-2'])
  assert.match(page,/selected:Map<string,RestrictionTarget>/)
  assert.match(page,/\[\.\.\.selected\.values\(\)\]/)
  assert.match(page,/aria-label=\{`移除 \$\{item\.name\}`\}/)
})

test('inactive existing selections remain visible and empty associations can save',()=>{
  assert.match(page,/!item\.is_active&&<em>已停用<\/em>/)
  assert.match(page,/setIngredients\(targetMap\(detail\.ingredients\)\)/)
  assert.match(page,/setDishes\(targetMap\(detail\.dishes\)\)/)
  assert.match(page,/ingredient_ids:\[\.\.\.ingredients\.keys\(\)\]/)
  assert.match(page,/dish_ids:\[\.\.\.dishes\.keys\(\)\]/)
})

test('bulk selection query carries current search category and active-only semantics',()=>{
  assert.equal(selection.bulkSelectionQuery(' 五花 ','meat-id'),'active=true&search=%E4%BA%94%E8%8A%B1&category_id=meat-id')
  assert.equal(selection.bulkSelectionQuery('',''),'active=true')
  assert.match(page,/selection-options\?\$\{bulkSelectionQuery\(search,categoryId\)\}/)
  assert.match(page,/全選目前篩選結果/)
  assert.match(page,/取消選取目前篩選結果/)
  assert.match(page,/目前篩選共 \{total\} 筆/)
})

test('bulk add spans pages without duplicates and bulk remove preserves other filters',()=>{
  const pork=Array.from({length:37},(_,index)=>({id:`p-${index}`,code:String(index),name:`豬肉 ${index}`,is_active:true}))
  const fish=Array.from({length:10},(_,index)=>({id:`f-${index}`,code:String(index),name:`魚肉 ${index}`,is_active:true}))
  let selected=selection.targetMap(fish)
  selected=selection.addTargets(selected,pork)
  selected=selection.addTargets(selected,pork.slice(0,20))
  assert.equal(selected.size,47)
  const remaining=selection.removeTargets(selected,pork)
  assert.deepEqual([...remaining.keys()],fish.map(item=>item.id))
  assert.equal(selected.size,47)
})
