import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const nutrition=readFileSync(new URL('../src/features/nutrition/NutritionPage.tsx',import.meta.url),'utf8')
const ingredients=readFileSync(new URL('../src/features/ingredients/IngredientsPage.tsx',import.meta.url),'utf8')
const numbers=readFileSync(new URL('../src/utils/numbers.ts',import.meta.url),'utf8')
const styles=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')

test('sidebar exposes nutrition between ingredients and dishes',()=>{assert.match(app,/\['ingredients','食材'\],\['nutrition','營養資料'\],\['dishes','菜色／配方'\]/)})
test('nutrition management switches official manual and import records',()=>{for(const label of ['官方食品資料庫','手動營養資料','匯入紀錄'])assert.match(nutrition,new RegExp(label))})
test('official food search filters and pagination stay server-side',()=>{assert.match(nutrition,/URLSearchParams/);assert.match(nutrition,/nutrition\/foods\?\$\{query\}/);assert.match(nutrition,/PaginationControls/)})
test('xlsx import uses app dialog preview summary and explicit confirm',()=>{assert.match(nutrition,/accept="\.xlsx/);assert.match(nutrition,/imports\/preview/);assert.match(nutrition,/確認正式匯入/);assert.match(nutrition,/本版未出現/)})
test('manual nutrition supports create edit and optional nutrient fields',()=>{assert.match(nutrition,/新增手動食品/);assert.match(nutrition,/修改手動營養食品/);assert.match(nutrition,/corrected_energy/);assert.match(nutrition,/sodium/)})
test('ingredient list exposes nutrition status and server-side filter',()=>{assert.match(ingredients,/營養狀態/);assert.match(ingredients,/nutrition_status=/);for(const label of ['官方','手動','未設定'])assert.match(ingredients,new RegExp(label))})
test('ingredient create continues directly into nutrition mapping',()=>{assert.match(ingredients,/setMapping\(created\)/);assert.match(ingredients,/台灣食品營養成分資料庫/);assert.match(ingredients,/手動營養食品/)})
test('ingredient edit can change or clear current mapping',()=>{assert.match(ingredients,/>變更</);assert.match(ingredients,/>清除對應</);assert.match(ingredients,/nutrition_food_id:null/)})
test('nutrition source radios stay beside their clickable labels',()=>{assert.match(ingredients,/fieldset className="nutrition-source-options"/);assert.match(styles,/\.nutrition-source-options label\{display:flex/);assert.match(styles,/\.nutrition-source-options input\{width:auto;min-width:auto/)})
test('corrected energy uses one shared two-decimal presentation formatter',()=>{assert.match(numbers,/formatNutritionValue/);assert.match(numbers,/maximumFractionDigits:2/);for(const source of [nutrition,ingredients])assert.match(source,/formatNutritionValue/)})
test('nutrition flows do not use native prompt or confirm',()=>{for(const source of [nutrition,ingredients])assert.doesNotMatch(source,/window\.(prompt|confirm)\s*\(/)})
