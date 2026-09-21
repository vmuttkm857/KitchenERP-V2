import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { requirementQuantityPresentation } from '../src/features/requirements/dailyRequirements.ts'

const page=readFileSync(new URL('../src/features/requirements/RequirementsPage.tsx',import.meta.url),'utf8')

test('weight presentation converts only exact g using decimal-safe strings',()=>{
  for(const [value,expected] of [['1','0.001'],['10','0.01'],['100','0.1'],['500','0.5'],['1000','1'],['1050','1.05'],['2100','2.1'],['12345','12.345'],['12500','12.5'],['17500','17.5'],['42000','42']]){
    assert.deepEqual(requirementQuantityPresentation(value,'g','kg'),{quantity:expected,unit:'kg'})
  }
  assert.deepEqual(requirementQuantityPresentation('8.4','kg','kg'),{quantity:'8.4',unit:'kg'})
  assert.deepEqual(requirementQuantityPresentation('300','片','kg'),{quantity:'300',unit:'片'})
  assert.deepEqual(requirementQuantityPresentation('100','個','kg'),{quantity:'100',unit:'個'})
})

test('original mode preserves inputs and conversion does not mutate source data',()=>{
  const source={quantity:'42000.000',unit:'g'}
  assert.deepEqual(requirementQuantityPresentation(source.quantity,source.unit,'original'),source)
  requirementQuantityPresentation(source.quantity,source.unit,'kg')
  assert.deepEqual(source,{quantity:'42000.000',unit:'g'})
})

test('requirements page shares one unit mode across tables copy and Excel export',()=>{
  assert.match(page,/useState<WeightUnitMode>\('original'\)/)
  assert.match(page,/原始單位/)
  assert.match(page,/重量換算 kg/)
  assert.match(page,/aria-pressed/)
  assert.match(page,/weight_unit_mode:weightUnitMode/)
  assert.match(page,/dailyRowsTsv\(result\.daily_rows,'daily',weightUnitMode\)/)
  assert.match(page,/supplierRowsTsv\(result\.daily_rows,supplierKey,weightUnitMode\)/)
  assert.match(page,/RequirementTable rows=\{result\.rows\} weightUnitMode=\{weightUnitMode\}/)
})
