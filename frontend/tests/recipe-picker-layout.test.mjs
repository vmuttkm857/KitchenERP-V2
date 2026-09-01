import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const editor=readFileSync(new URL('../src/features/recipes/RecipeEditor.tsx',import.meta.url),'utf8')
const styles=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')

test('recipe ingredient picker follows the intended field order',()=>{
  const labels=['搜尋食材','選擇食材','食材分類','供應商']
  const positions=labels.map(label=>editor.indexOf(`>${label}<`))
  assert.ok(positions.every(position=>position>=0))
  assert.deepEqual([...positions].sort((left,right)=>left-right),positions)
})

test('recipe ingredient picker keeps existing search filter selector behavior',()=>{
  assert.match(editor,/setIngredientSearch/)
  assert.match(editor,/categoryId:ingredientCategory/)
  assert.match(editor,/supplierId:ingredientSupplier/)
  assert.match(editor,/value=\{selectedIngredient\}/)
  assert.match(editor,/onClick=\{addIngredient\}/)
  assert.match(editor,/PaginationControls/)
})

test('recipe ingredient picker is four columns then two and one responsively',()=>{
  assert.match(styles,/\.recipe-picker-filtered \{ grid-template-columns:minmax\(14rem,1\.45fr\) minmax\(15rem,1\.35fr\) minmax\(10rem,\.85fr\) minmax\(11rem,1fr\)/)
  assert.match(styles,/@media\(max-width:1100px\)\{\.recipe-picker-filtered\{grid-template-columns:minmax\(0,1fr\) minmax\(0,1fr\)\}/)
  assert.match(styles,/@media\(max-width:680px\)\{\.recipe-picker-filtered\{grid-template-columns:minmax\(0,1fr\)\}\}/)
})
