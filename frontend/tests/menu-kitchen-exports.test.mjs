import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const menu=readFileSync(new URL('../src/features/menus/MenuEditor.tsx',import.meta.url),'utf8')
const kitchen=readFileSync(new URL('../src/features/kitchen_operations/KitchenOperationsPage.tsx',import.meta.url),'utf8')

test('menu editor provides weekly layouts, formats, and explicit paper choices',()=>{
  assert.match(menu,/>匯出</)
  assert.match(menu,/餐別合併週表/)
  assert.match(menu,/菜色分格週表/)
  assert.match(menu,/漂亮公告版/)
  assert.match(menu,/PDF（圖片型）/)
  assert.match(menu,/單張 A4/)
  assert.match(menu,/4張 A4 拼接放大/)
  assert.match(menu,/role="dialog"/)
})

test('menu export composes the selected authenticated endpoint and handles loading errors',()=>{
  assert.match(menu,/\/exports\/menus\/\$\{menu\.id\}\/\$\{exportLayout\}\/\$\{exportFormat\}/)
  assert.match(menu,/exporting \? '匯出中…' : '匯出'/)
  assert.match(menu,/菜單匯出失敗/)
})

test('kitchen weekly prep uses one format and paper dialog with the dedicated endpoint',()=>{
  assert.match(kitchen,/週配料表/)
  assert.match(kitchen,/\/exports\/kitchen-operations\/simple\/\$\{simpleFormat\}/)
  assert.match(kitchen,/simpleExporting\?'匯出中…':'匯出'/)
  assert.match(kitchen,/週配料表下載失敗/)
  assert.match(kitchen,/4張 A4 拼接放大/)
})

test('new export flows do not use native prompt confirm or alert',()=>{
  for(const source of [menu,kitchen]){
    assert.doesNotMatch(source,/window\.(prompt|confirm|alert)\s*\(/)
  }
})
