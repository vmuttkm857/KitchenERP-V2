import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const page=readFileSync(new URL('../src/features/postpartum/PostpartumConflictPage.tsx',import.meta.url),'utf8')
const handling=readFileSync(new URL('../src/features/postpartum/PostpartumConflictHandling.tsx',import.meta.url),'utf8')
const types=readFileSync(new URL('../src/features/postpartum/conflictTypes.ts',import.meta.url),'utf8')
const css=readFileSync(new URL('../src/features/postpartum/PostpartumConflictPage.css',import.meta.url),'utf8')
const compiledTypes=ts.transpileModule(types,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const typeHelpers=await import(`data:text/javascript;base64,${Buffer.from(compiledTypes).toString('base64')}`)

test('pending conflicts are independently selectable by case and menu dish within one meal',()=>{
  assert.match(page,/result\.outcome==='conflict'/)
  assert.match(page,/handled\.status==='pending'/)
  assert.match(page,/type="checkbox" aria-label=\{`選取/)
  assert.match(handling,/return `\$\{meal\}:\$\{caseId\}:\$\{menuDishId\}`/)
  assert.match(page,/selectedMeal!==null&&selectedMeal!==entry\.meal\.postpartum_meal/)
  assert.match(page,/已選 \{selected\.size\} 個衝突項目/)
})

test('selection invariant rejects mixed meals in state and both batch actions',()=>{
  const breakfast=[{meal:'breakfast'},{meal:'breakfast'}]
  assert.equal(typeHelpers.selectionMatchesMeal(breakfast,'breakfast'),true)
  assert.equal(typeHelpers.selectionMatchesMeal([{meal:'breakfast'},{meal:'lunch'}],'breakfast'),false)
  assert.equal(typeHelpers.selectionMatchesMeal([],null),false)
  assert.match(page,/if\(currentMeal!==null&&item\.meal!==currentMeal\)return current/)
  assert.match(page,/function validSelectedItems\(\).*selectionMatchesMeal\(items,selectedMeal\).*clearSelection\(\);return null/s)
  assert.match(page,/function openReplacement\(\)\{const items=validSelectedItems\(\);if\(!items\)return;/)
  assert.match(page,/function openAcknowledgement\(\)\{if\(!validSelectedItems\(\)\)return;/)
  assert.match(page,/onClick=\{openReplacement\}/)
  assert.match(page,/onClick=\{openAcknowledgement\}/)
})

test('date meal and view navigation clear cross-slot selection',()=>{
  assert.match(page,/function clearSelection\(\)/)
  assert.match(page,/function changeDate\(value:string\).*clearSelection\(\)/)
  assert.match(page,/function chooseMeal\(meal:MealFilter\)\{clearSelection\(\)/)
  assert.match(page,/function chooseView\(next:ViewMode\)\{clearSelection\(\)/)
  assert.match(page,/function openDay\(date:string,meal:Meal\).*clearSelection\(\)/)
})

test('candidate search is server paged and sends the exact selected conflict identities',()=>{
  for(const token of ['target_date:targetDate','postpartum_meal:meal','items:chosenItems.map(item=>item.item)','page,page_size:20','search:search||null','category_id:categoryId||null'])assert.match(handling,new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')))
  assert.match(handling,/\/postpartum\/replacement-candidates\/search/)
  assert.match(handling,/\/categories\/dish\?active=true&page_size=100/)
  assert.match(handling,/requestSequence\.current/)
  assert.match(handling,/共 \{total\} 筆／第 \{page\} 頁／共 \{pages\} 頁/)
})

test('replacement dialog presents three compact steps without a duplicate selected summary',()=>{
  for(const label of ['① 選擇要一起處理的衝突','② 選擇共同替代菜','③ 確認','已選 {chosenItems.length} 項'])assert.match(handling,new RegExp(label.replace(/[{}]/g,'\\$&')))
  assert.match(handling,/const visibleItems=showAllItems\?orderedAvailable:/)
  assert.match(handling,/currentGroupItems,\.\.\.otherItems\.slice/)
  assert.match(handling,/顯示其他 \$\{hiddenItemCount\} 項/)
  assert.doesNotMatch(handling,/<SelectedItems items=\{chosenItems\}/)
  assert.match(handling,/<SelectedItems items=\{items\}/)
  assert.match(css,/postpartum-replacement-item-picker\{display:grid;gap:/)
  assert.match(css,/postpartum-replacement-footer\{position:sticky/)
})

test('replacement conflict items use stable compact columns without vertical Chinese wrapping',()=>{
  for(const className of ['postpartum-replacement-item-row','postpartum-replacement-item-case','postpartum-replacement-item-dish','postpartum-replacement-item-groups'])assert.match(handling,new RegExp(className))
  assert.match(handling,/item\.caseItem\.current_room/)
  assert.match(handling,/item\.caseItem\.name/)
  assert.match(handling,/item\.dish\.dish\.name/)
  assert.match(handling,/groups\.map\(group=><small/)
  assert.match(css,/postpartum-replacement-item-row\{display:grid!important;grid-template-columns:1\.1rem minmax\(9rem,12rem\) minmax\(8rem,1fr\) auto;align-items:center/)
  assert.match(css,/min-height:46px/)
  assert.match(css,/postpartum-replacement-item-case,\.postpartum-replacement-item-dish\{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap/)
  assert.match(css,/postpartum-replacement-item-groups small\{[^}]*white-space:nowrap/)
  assert.match(css,/postpartum-replacement-dialog\{width:min\(960px,calc\(100vw - 48px\)\)/)
})

test('known-conflict candidates are collapsed per server page and remain disabled',()=>{
  assert.match(handling,/const selectableCandidates=candidates\.filter\(item=>item\.status!=='conflict'\)/)
  assert.match(handling,/const conflictCandidates=candidates\.filter\(item=>item\.status==='conflict'\)/)
  assert.match(handling,/顯示本頁 \$\{conflictCandidates\.length\} 道不可使用菜色/)
  assert.match(handling,/showConflictCandidates&&<div className="postpartum-candidate-list"/)
  assert.match(handling,/disabled=\{item\.status==='conflict'\}/)
  assert.match(handling,/selectableCandidates\.map\(candidateRow\)/)
  assert.match(handling,/selectableCandidates\.length===0\?<div className="state-panel empty-state postpartum-candidate-page-empty"/)
  assert.match(handling,/本頁沒有可直接使用的替代菜/)
  assert.match(handling,/本頁 \{conflictCandidates\.length\} 道菜皆命中禁忌/)
  assert.match(handling,/<div className="pagination">/)
  assert.ok(handling.indexOf('<div className="pagination">')>handling.indexOf('selectableCandidates.length===0'))
})

test('candidate states prevent known conflicts and warn before insufficient-recipe confirmation',()=>{
  assert.match(handling,/disabled=\{item\.status==='conflict'\}/)
  assert.match(handling,/明確命中禁忌，不可選擇/)
  assert.match(handling,/未發現已知禁忌，但資料不足，請人工確認/)
  assert.match(handling,/return '未發現已知禁忌'/)
  assert.match(handling,/此菜餚配方資料不足，系統無法完整確認禁忌，需人工確認/)
  assert.match(handling,/命中：/)
})

test('candidate warnings are deduplicated from structured restriction data with a fallback',()=>{
  const group={id:'group-1',name:'不內臟',color:'#000',notes:null,is_active:true}
  const caseItem={id:'case-1',case_number:'01',name:'王○○',current_room:'501',status:'active',restriction_groups:[group],warnings:[]}
  const structured={code:'RESTRICTION_GROUP_NOTE_ONLY',message:'technical one',case_id:'case-1',restriction_group_id:'group-1'}
  const fallback={code:'DISH_RECIPE_EMPTY',message:'此菜沒有配方食材'}
  const candidate={dish:{id:'dish',code:'01',name:'替代菜',is_active:true},status:'insufficient_recipe_data',coverage:'partial',review_needed:true,case_results:[{case_id:'case-1',menu_dish_id:'menu-dish',outcome:'unknown',coverage:'partial',reasons:[],warnings:[structured,structured,fallback]}],warnings:[structured,fallback]}
  const presentation=typeHelpers.candidateWarningPresentation(candidate,[caseItem])
  assert.equal(presentation.count,2)
  assert.deepEqual(presentation.caseGroups[0].groups,['不內臟'])
  assert.deepEqual(presentation.fallbackMessages,['此菜沒有配方食材'])
})

test('candidate cards keep warning details collapsed behind a human-readable summary',()=>{
  assert.match(handling,/candidateWarningPresentation\(item,/)
  assert.match(handling,/\{review\.count\} 項需要人工確認/)
  assert.match(handling,/expanded\?'收合詳情':'查看詳情'/)
  assert.match(handling,/以下禁忌目前缺少足夠資料，系統無法確認/)
  assert.match(handling,/review\.caseGroups\.map/)
  assert.match(handling,/review\.fallbackMessages\.map/)
  const candidateRow=handling.slice(handling.indexOf('function candidateRow'),handling.indexOf('async function save'))
  assert.doesNotMatch(candidateRow,/<WarningLines/)
  assert.match(css,/postpartum-candidate-row\{display:grid;[^}]*min-height:58px/)
})

test('insufficient recipe candidates require a fresh explicit acknowledgement before save',()=>{
  assert.equal(typeHelpers.candidateNeedsRecipeAcknowledgement('insufficient_recipe_data'),true)
  assert.equal(typeHelpers.candidateNeedsRecipeAcknowledgement('no_known_conflict'),false)
  assert.equal(typeHelpers.candidateNeedsRecipeAcknowledgement('conflict'),false)
  assert.match(handling,/const \[insufficientAcknowledged,setInsufficientAcknowledged\]=useState\(false\)/)
  assert.match(handling,/function chooseCandidate\(item:ReplacementCandidate\)\{setCandidate\(item\);setInsufficientAcknowledged\(false\)\}/)
  assert.match(handling,/onChange=\{\(\)=>chooseCandidate\(item\)\}/)
  assert.match(handling,/我已確認此菜餚配方資料不足，仍要使用此替代菜/)
  assert.equal((handling.match(/needsRecipeAcknowledgement&&!insufficientAcknowledged/g)??[]).length,2)
  assert.match(handling,/const \[candidate,setCandidate\]=useState<ReplacementCandidate\|null>\(initial\?/)
})

test('replacement create update explicit reassign and authoritative refresh are wired',()=>{
  assert.match(handling,/method:initial\?'PUT':'POST'/)
  assert.match(handling,/\/postpartum\/replacement-groups\/\$\{initial\.id\}/)
  assert.match(handling,/reassign_items:reassign/)
  assert.match(handling,/useState\(false\)/)
  assert.match(handling,/我確認將所選衝突項目移至此共同替代群組/)
  assert.match(handling,/await onSaved\(\)/)
  assert.match(page,/await refreshAuthoritative\(\)/)
  assert.match(handling,/cause\.status===409\|\|cause\.status===422/)
})

test('handled conflicts remain visible with group details acknowledgement and POST cancellation',()=>{
  for(const token of ['已替代','需要重新確認','人工確認｜不需替代','修改','取消替代','取消確認'])assert.match(handling,new RegExp(token))
  assert.match(page,/replacement-groups\/\$\{group\.id\}\/cancel`,\{method:'POST'\}/)
  assert.match(page,/conflict-acknowledgements\/\$\{item\.id\}\/cancel`,\{method:'POST'\}/)
  assert.match(handling,/\/postpartum\/conflict-acknowledgements/)
  assert.match(handling,/for\(const item of items\)/)
  assert.match(handling,/成功 \$\{success\} 項；失敗 \$\{failures\.length\} 項/)
  assert.doesNotMatch(page,/method:'DELETE'/)
})

test('handled dish rows resolve their owning handling and expose authoritative edit paths',()=>{
  const group={id:'group',items:[{case_id:'case-1',original_menu_dish_id:'dish-1'}]}
  const acknowledgement={id:'ack',case_id:'case-2',original_menu_dish_id:'dish-2'}
  const response={conflict_items:[
    {case_id:'case-1',original_menu_dish_id:'dish-1',status:'replaced'},
    {case_id:'case-2',original_menu_dish_id:'dish-2',status:'manually_acknowledged'},
  ],replacement_groups:[group],manual_acknowledgements:[acknowledgement]}
  assert.equal(typeHelpers.findHandlingContext(response,'case-1','dish-1').replacementGroup,group)
  assert.equal(typeHelpers.findHandlingContext(response,'case-2','dish-2').acknowledgement,acknowledgement)
  assert.equal(typeHelpers.findHandlingContext(response,'case-3','dish-3').status,null)
  assert.match(page,/const context=findHandlingContext\(handling,entry\.caseItem\.id,result\.menu_dish_id\),handled=context\.status/)
  assert.match(page,/pending&&dish&&<input type="checkbox"/)
  assert.match(page,/context\.replacementGroup&&handled\?\.status!=='pending'/)
  assert.match(page,/\?\s*'重新確認':'修改處理'/)
  assert.match(page,/context\.acknowledgement&&handled\?\.status!=='pending'/)
  assert.match(page,/>重新處理<\/button>/)
  assert.match(page,/function editReplacementGroup\(group:ReplacementGroup\)/)
  assert.match(page,/onReprocessAcknowledgement=\{item=>void cancelAcknowledgement\(item\)\}/)
  assert.match(page,/確定取消人工確認，將此衝突恢復為待處理/)
  assert.match(page,/await refreshAuthoritative\(\)/)
})

test('types and styling distinguish all handling states without relying on color alone',()=>{
  for(const state of ['pending','replaced','manually_acknowledged','requires_reconfirmation'])assert.match(types,new RegExp(state))
  for(const state of ['no_known_conflict','conflict','insufficient_recipe_data'])assert.match(types,new RegExp(state))
  assert.match(css,/postpartum-conflict-selection-bar/)
  assert.match(css,/postpartum-handling-overview/)
  assert.match(css,/postpartum-handling-status\.is-requires_reconfirmation/)
})
