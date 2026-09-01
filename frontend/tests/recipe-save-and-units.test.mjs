import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const blocker=readFileSync(new URL('../src/app/NavigationBlocker.tsx',import.meta.url),'utf8')
const editor=readFileSync(new URL('../src/features/recipes/RecipeEditor.tsx',import.meta.url),'utf8')
const ingredients=readFileSync(new URL('../src/features/ingredients/IngredientsPage.tsx',import.meta.url),'utf8')
const unitSource=readFileSync(new URL('../src/utils/units.ts',import.meta.url),'utf8')

test('recipe save-and-return synchronously clears the guard only after save succeeds',()=>{
  assert.match(blocker,/dirtyRef\.current = value/)
  assert.match(blocker,/attemptNavigation\(dirtyRef\.current, action\)/)
  assert.match(editor,/const saved=await apiRequest<Recipe>/)
  assert.match(editor,/if\(returnAfter\)completeSavedNavigation\(clearEditorDirty,onClose\)/)
  assert.doesNotMatch(editor,/setTimeout\s*\(/)
})

test('ordinary recipe return remains guarded and save failure does not navigate',()=>{
  assert.match(editor,/function requestClose\(\)\{onClose\(\)\}/)
  assert.match(editor,/onClick=\{requestClose\}/)
  assert.match(blocker,/onClick=\{\(\) => setPendingAction\(null\)\}>留在此頁/)
  assert.match(blocker,/confirmNavigation\(action\)/)
  const catchBranch=editor.slice(editor.indexOf('catch(cause)'),editor.indexOf('finally{setSaving(false)}'))
  assert.doesNotMatch(catchBranch,/onClose|completeSavedNavigation|setDirty\(false\)/)
  assert.match(editor,/if\(returnAfter\)completeSavedNavigation\(clearEditorDirty,onClose\);else setMessage\('配方已儲存'\)/)
})

test('ingredient and recipe selectors share the legal package unit',()=>{
  for(const unit of ['g','kg','斤','片','個','隻','包','盒','箱','ml','L','罐','桶'])assert.match(unitSource,new RegExp(`['"]${unit}['"]`))
  assert.match(ingredients,/erpUnits\.map/)
  assert.match(editor,/erpUnits\.includes/)
})
