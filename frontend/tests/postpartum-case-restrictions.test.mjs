import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumCasesPage.tsx',import.meta.url),'utf8')
const dialog=readFileSync(new URL('../src/features/postpartum/CaseRestrictionsDialog.tsx',import.meta.url),'utf8')
const source=readFileSync(new URL('../src/features/postpartum/caseRestrictionState.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText
const state=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

const active=(id,name,color='#AA2200')=>({id,name,color,is_active:true})
const inactive=(id,name,color='#777777')=>({id,name,color,is_active:false})

test('case list and detail render compact restriction badges and empty states',()=>{
  assert.match(page,/<th>飲食禁忌<\/th>/)
  assert.match(page,/CaseRestrictionBadges groups=\{item\.restriction_groups\}/)
  assert.match(dialog,/groups\.map\(group=>/)
  assert.doesNotMatch(page,/limit=\{/)
  assert.doesNotMatch(dialog,/groups\.slice|case-restriction-more|groups\.length>limit/)
  assert.match(dialog,/borderColor:group\.color/)
  assert.match(dialog,/\{group\.name\}/)
  assert.match(page,/未設定飲食禁忌/)
  assert.match(page,/CaseRestrictionBadges groups=\{detail\.restriction_groups\}/)
})

test('case list keeps all eight assigned restriction names without a +N summary',()=>{
  const groups=Array.from({length:8},(_,index)=>active(String(index),`禁忌${index+1}`))
  const rendered=state.mergeRestrictionGroups([],groups).map(item=>item.name)
  assert.equal(rendered.length,8)
  for(const group of groups)assert.ok(rendered.includes(group.name))
  assert.doesNotMatch(dialog,/\+\{groups\.length/)
})

test('manage modal is independent and saves replace-all assignments',()=>{
  assert.match(page,/CaseRestrictionsDialog/)
  assert.match(page,/管理禁忌/)
  assert.match(dialog,/管理飲食禁忌/)
  assert.match(dialog,/method:'PUT'/)
  assert.match(dialog,/restriction_group_ids:\[\.\.\.selected\.keys\(\)\]/)
  assert.match(dialog,/onSaved\(response\.restriction_groups\)/)
  assert.match(page,/setItems\(values=>values\.map/)
  assert.match(page,/setDetail\(value=>value&&value\.case\.id/)
})

test('selection supports multiple, deselect, clear and immutable cancel state',()=>{
  const beef=active('1','不牛'),fish=active('2','不魚')
  const persisted=state.restrictionMap([beef])
  let draft=state.toggleRestrictionSelection(persisted,fish)
  assert.deepEqual([...draft.keys()],['1','2'])
  assert.deepEqual([...persisted.keys()],['1'])
  draft=state.toggleRestrictionSelection(draft,beef)
  assert.deepEqual([...draft.keys()],['2'])
  draft=state.toggleRestrictionSelection(draft,fish)
  assert.equal(draft.size,0)
  assert.deepEqual([...persisted.keys()],['1'])
})

test('inactive assigned group remains visible and removable but cannot be newly selected',()=>{
  const retired=inactive('3','不奶')
  const options=state.mergeRestrictionGroups([active('1','不牛')],[retired])
  assert.ok(options.some(item=>item.id==='3'&&!item.is_active))
  const selected=state.restrictionMap([retired])
  const removed=state.toggleRestrictionSelection(selected,retired)
  assert.equal(removed.has('3'),false)
  const readded=state.toggleRestrictionSelection(removed,retired)
  assert.equal(readded.has('3'),false)
  assert.match(dialog,/disabled=\{!group\.is_active&&!checked\}/)
  assert.match(dialog,/已停用/)
})

test('search filters options without clearing selected state',()=>{
  const values=[active('1','不牛'),active('2','不魚'),active('3','不內臟')]
  const selected=state.restrictionMap(values.slice(0,2))
  assert.deepEqual(state.filterRestrictionGroups(values,'魚').map(item=>item.id),['2'])
  assert.deepEqual([...selected.keys()],['1','2'])
  assert.match(dialog,/setSearch\(event\.target\.value\)/)
  assert.doesNotMatch(dialog,/setSearch\([^)]*\).*setSelected/)
})

test('create edit and restriction management keep separate state',()=>{
  assert.match(page,/createForm,setCreateForm/)
  assert.match(page,/editingCase,setEditingCase/)
  assert.match(page,/restrictionCase,setRestrictionCase/)
  assert.match(page,/restrictionGroups,setRestrictionGroups/)
  assert.doesNotMatch(page,/CaseFields[^\n]*restriction/)
})
