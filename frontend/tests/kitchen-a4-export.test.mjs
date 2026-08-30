import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source=readFileSync(new URL('../src/features/kitchen_operations/KitchenOperationsPage.tsx',import.meta.url),'utf8')

test('kitchen operations exposes an independent A4 workbook download',()=>{
  assert.match(source,/\/exports\/kitchen-operations\/a4-xlsx/)
  assert.match(source,/下載 A4 廚房作業表/)
  assert.match(source,/A4 廚房作業表下載失敗/)
})

test('existing Excel and PDF downloads remain available',()=>{
  assert.match(source,/下載 Excel/)
  assert.match(source,/下載 PDF/)
  assert.match(source,/\/exports\/kitchen-operations\/\$\{format\}/)
})
