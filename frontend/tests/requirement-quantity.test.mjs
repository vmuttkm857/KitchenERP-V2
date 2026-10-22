import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { requirementQuantityPresentation } from '../src/features/requirements/dailyRequirements.ts'

const page=readFileSync(new URL('../src/features/requirements/RequirementsPage.tsx',import.meta.url),'utf8')
const snapshotsPage=readFileSync(new URL('../src/features/snapshots/SnapshotsPage.tsx',import.meta.url),'utf8')
const globalCss=readFileSync(new URL('../src/styles/global.css',import.meta.url),'utf8')

test('weight presentation preserves existing g behavior and opt-in jin uses project-defined conversion',()=>{
  for(const [value,expected] of [['1','0.001'],['10','0.01'],['100','0.1'],['500','0.5'],['1000','1'],['1050','1.05'],['2100','2.1'],['12345','12.345'],['12500','12.5'],['17500','17.5'],['42000','42']]){
    assert.deepEqual(requirementQuantityPresentation(value,'g','kg'),{quantity:expected,unit:'kg'})
  }
  for(const [value,expected] of [['1','0.6'],['2','1.2'],['2.5','1.5'],['10','6'],['12.345','7.407']]){
    assert.deepEqual(requirementQuantityPresentation(value,'斤','kg',true),{quantity:expected,unit:'kg'})
  }
  assert.deepEqual(requirementQuantityPresentation('2','斤','kg'),{quantity:'2',unit:'斤'})
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

test('snapshot page shares the display-only unit mode across daily supplier and total views',()=>{
  assert.match(snapshotsPage,/useState<WeightUnitMode>\('original'\)/)
  assert.match(snapshotsPage,/原始單位/)
  assert.match(snapshotsPage,/重量換算 kg/)
  assert.match(snapshotsPage,/aria-pressed/)
  assert.match(snapshotsPage,/supplierRowsTsv\(snapshotDailyRows\(detail\.items\),supplierKey,weightUnitMode,true\)/)
  assert.match(snapshotsPage,/SnapshotDailyTable rows=\{sortDailyRows\(snapshotDailyRows\(detail\.items\),'daily'\)\} showSupplier weightUnitMode=\{weightUnitMode\}/)
  assert.match(snapshotsPage,/SnapshotDailyTable rows=\{filterSupplierRows\(snapshotDailyRows\(detail\.items\),supplierKey\)\} toneRows=\{snapshotDailyRows\(detail\.items\)\} showSupplier=\{false\} weightUnitMode=\{weightUnitMode\}/)
  assert.match(snapshotsPage,/SnapshotTotalTable items=\{detail\.items\} weightUnitMode=\{weightUnitMode\}/)
  assert.match(snapshotsPage,/requirementQuantityPresentation\([^\n]+weightUnitMode,true\)/)
  assert.doesNotMatch(snapshotsPage,/apiDownload\([^\n]*weightUnitMode/)
})

test('weight unit toggle has scoped readable active inactive hover focus and disabled colors',()=>{
  assert.match(globalCss,/\.requirement-weight-unit-toggle button\{color:#245536;background:#edf4ef;border:1px solid #b8cdbd\}/)
  assert.match(globalCss,/\.requirement-weight-unit-toggle button\.active,\.requirement-weight-unit-toggle button\[aria-pressed="true"\]\{color:#fff;background:#2f6840;border-color:#2f6840/)
  assert.match(globalCss,/\.requirement-weight-unit-toggle button:hover:not\(:disabled\)/)
  assert.match(globalCss,/\.requirement-weight-unit-toggle button:focus-visible\{outline:3px solid/)
  assert.match(globalCss,/\.requirement-weight-unit-toggle button:disabled\{color:#66736b;background:#e6ebe7/)
  assert.doesNotMatch(globalCss,/\.requirement-weight-unit-toggle[^\n]*!important/)
})
