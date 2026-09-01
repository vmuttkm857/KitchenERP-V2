import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const app=read('../src/app/App.tsx')
const dishes=read('../src/features/dishes/DishesPage.tsx')
const menuEditor=read('../src/features/menus/MenuEditor.tsx')
const page=read('../src/features/production/ProductionProfilePage.tsx')
const plan=read('../src/features/production/MenuProductionDialog.tsx')
const presentation=read('../src/features/production/presentation.ts')
const client=read('../src/api/client.ts')
const styles=read('../src/styles/global.css')
const {aggregateBatches,durationFromInput,durationToInput,formatDuration,formatProductionNumber}=await import('../src/features/production/presentation.ts')

test('dish management opens a full recipe-card work page instead of a dialog',()=>{
  assert.match(dishes,/onEditProduction\(item\)/)
  assert.doesNotMatch(dishes,/ProductionProfileDialog|productionDish/)
  assert.match(app,/page==='production-profile'.*<ProductionProfilePage/)
  assert.match(page,/← 返回菜色管理/)
  assert.doesNotMatch(page,/modal-backdrop|role="dialog"|aria-modal/)
  assert.doesNotMatch(styles,/\.production-dialog/)
})

test('first creation is a four-step guided flow with recipe seeding',()=>{
  for(const label of ['設定每批人數','選擇常用份數','確認食材用量','建立製作步驟'])assert.match(page,new RegExp(label))
  assert.match(page,/\[10,30,50,100\]/)
  assert.match(page,/createProfileAndVersions/)
  assert.match(page,/食材用量已依標準配方帶入/)
})

test('missing profile is a normal empty state and real errors remain distinct',()=>{
  assert.match(page,/cause instanceof ApiError&&cause\.status===404/)
  assert.match(page,/setProfile\(null\)/)
  assert.match(page,/尚未建立標準食譜卡/)
  assert.match(page,/>建立標準食譜卡</)
  assert.match(page,/標準食譜卡載入失敗，請稍後重試/)
  assert.match(page,/標準食譜卡載入中/)
})

test('established cards separate the five maintenance sections',()=>{
  for(const label of ['基本設定','常用製作份數','食材用量','製作步驟','製作計畫預覽'])assert.match(page,new RegExp(label))
  assert.match(page,/production-tabs/)
  assert.match(styles,/\.production-tabs/)
})

test('versions are summary cards with official and draft controls',()=>{
  assert.match(page,/version-card-grid/)
  assert.match(page,/可正式使用/)
  assert.match(page,/編輯中/)
  assert.match(page,/查看／編輯/)
  assert.match(page,/複製/)
  assert.match(page,/設為可正式使用/)
})

test('ingredient quantities use readable presentation and inline editing',()=>{
  assert.match(page,/formatProductionNumber\(item\.quantity\)/)
  assert.match(presentation,/maximumFractionDigits:6/)
  assert.match(page,/這個份數需要/)
  assert.match(page,/用途/)
  assert.match(page,/最後加入/)
})

test('process steps start collapsed and progressively reveal relevant fields',()=>{
  assert.match(page,/const \[expanded,setExpanded\]=useState\(false\)/)
  assert.match(page,/這一步要做哪一類工作？/)
  assert.match(page,/timedSteps\.has/)
  assert.match(page,/heatedSteps\.has/)
  assert.match(page,/temperatureSteps\.has/)
  assert.match(page,/traySteps\.has/)
  assert.match(page,/顯示其他設定/)
})

test('duration input is human-friendly while preserving duration_seconds',()=>{
  assert.match(page,/需要多久/)
  assert.match(page,/時間單位/)
  assert.match(page,/duration_seconds:durationFromInput/)
  assert.match(presentation,/seconds%3600===0/)
  assert.match(presentation,/seconds%60===0/)
  assert.match(presentation,/小時/)
  assert.match(presentation,/分鐘/)
})

test('production presentation helpers format actual kitchen values',()=>{
  assert.equal(formatProductionNumber('350.000000'),'350')
  assert.equal(formatProductionNumber('43.318400'),'43.3184')
  assert.deepEqual(durationToInput(1800),{value:'30',unit:'minutes'})
  assert.deepEqual(durationToInput(7200),{value:'2',unit:'hours'})
  assert.equal(durationFromInput('1.5','minutes'),90)
  assert.equal(formatDuration(90),'1 分鐘 30 秒')
  assert.deepEqual(aggregateBatches([{serving_count:100,official:true},{serving_count:100,official:true},{serving_count:6,official:false}]),[{serving_count:100,official:true,count:2},{serving_count:6,official:false,count:1}])
})

test('tray capacity gives a computed kitchen-facing hint',()=>{
  assert.match(page,/每盤可裝幾人份/)
  assert.match(page,/一次可放幾盤/)
  assert.match(page,/一次可處理約/)
  assert.match(page,/servings_per_tray\*value\.trays_per_batch/)
})

test('empty versions, ingredients, steps and preview have actionable wording',()=>{
  for(const text of ['尚未建立常用份數','尚未帶入食材','尚未建立製作步驟','尚未產生預覽'])assert.match(page,new RegExp(text))
})

test('preview aggregates identical batches and labels estimates clearly',()=>{
  assert.match(page,/aggregateBatches\(preview\.batches\)/)
  assert.match(page,/人份 × \{group\.count\} 批/)
  assert.match(page,/使用正式版本/)
  assert.match(page,/需要估算，請確認/)
})

test('menu production remains menu-driven and concise',()=>{
  assert.match(menuEditor,/MenuProductionDialog/)
  assert.match(plan,/全日（全部餐別）/)
  assert.match(plan,/\/menus\/\$\{menu\.id\}\/production-plan/)
  assert.match(plan,/已建立標準食譜卡/)
  assert.match(plan,/aggregateBatches\(dish\.batches\)/)
  assert.match(plan,/useState<'work'\|'detailed'>\('work'\)/)
  assert.match(plan,/廚房工作版/)
  assert.match(plan,/詳細標準版/)
  assert.match(plan,/mode=\$\{format\}/)
  assert.match(plan,/下載廚房工作單/)
  assert.match(plan,/下載詳細標準食譜/)
  assert.match(plan,/尚未建立標準食譜卡；PDF 仍會保留此菜與提醒/)
  assert.doesNotMatch(plan,/搜尋菜色|選擇菜色/)
})

test('existing authenticated API routes and PDF export remain unchanged',()=>{
  assert.match(page,/\/dishes\/\$\{dish\.id\}\/production-profile/)
  assert.match(page,/apiBlobUrl/)
  assert.match(plan,/\/exports\/menus\/\$\{menu\.id\}\/recipe-cards\/pdf/)
  assert.match(client,/Authorization.*Bearer/)
})

test('responsive work page avoids fixed width and horizontal page overflow',()=>{
  assert.match(styles,/\.production-page\{min-width:0;max-width:/)
  assert.match(styles,/@media\(max-width:900px\)/)
  assert.match(styles,/@media\(max-width:620px\)/)
  assert.doesNotMatch(styles,/production-page[^}]*overflow-x:scroll/)
})
