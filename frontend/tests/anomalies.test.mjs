import assert from 'node:assert/strict'
import test from 'node:test'

import { anomalySummary,formatAnomaly,groupAnomalies } from '../src/components/anomalies/anomalies.ts'

const incompatible=(ingredientId='ingredient-1')=>({
  code:'INCOMPATIBLE_UNIT',severity:'error',message:'Recipe unit cannot be safely converted',
  related_entity_id:ingredientId,related_entity_name:`食材-${ingredientId}`,
  context:{dish_id:'dish-1',dish_name:'測試菜色',recipe_unit:'盒',base_unit:'g',menu_date:'2026-08-17',meal_type_name:'午餐'},
})

test('19 repeated incompatible-unit occurrences become one group',()=>{
  const groups=groupAnomalies(Array.from({length:19},()=>incompatible()))
  assert.equal(groups.length,1)
  assert.equal(groups[0].count,19)
  assert.equal(anomalySummary(groups),'1 個問題（影響 19 筆）／0 個提醒')
})

test('different ingredients are not merged',()=>{
  assert.equal(groupAnomalies([incompatible('ingredient-1'),incompatible('ingredient-2')]).length,2)
})

test('missing supplier is grouped by ingredient',()=>{
  const anomaly={code:'MISSING_SUPPLIER',severity:'warning',message:'missing',related_entity_id:'ingredient-1',related_entity_name:'測試食材'}
  const groups=groupAnomalies([anomaly,anomaly,anomaly])
  assert.equal(groups.length,1)
  assert.equal(groups[0].count,3)
})

test('warning and error remain separate groups',()=>{
  const source={code:'FUTURE_CODE',message:'safe message',related_entity_id:'same'}
  const groups=groupAnomalies([{...source,severity:'warning'},{...source,severity:'error'}])
  assert.equal(groups.length,2)
  assert.deepEqual(groups.map(group=>group.severity).sort(),['error','warning'])
})

test('unknown anomaly code uses a safe fallback',()=>{
  const formatted=formatAnomaly({code:'FUTURE_CODE',severity:'warning',message:'可安全顯示的訊息'})
  assert.deepEqual(formatted,{title:'資料異常',description:'可安全顯示的訊息'})
})
