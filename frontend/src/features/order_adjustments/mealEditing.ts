import type { MenuAggregate } from '../menus/types'
import type { OrderingAdjustmentDetail, OrderingAdjustmentSyncPreview } from './types'

export interface AdjustmentMealTarget { menuId:string; date:string; mealTypeId:string }

export function validAdjustmentMealTarget(detail:OrderingAdjustmentDetail,target:AdjustmentMealTarget,layout:MenuAggregate|undefined) {
  const criteria=detail.criteria
  return detail.status==='draft'&&detail.purchase_locked===false
    &&criteria.menu_ids.includes(target.menuId)&&detail.source_menus.some(menu=>menu.menu_id===target.menuId)
    &&layout?.menu.id===target.menuId&&layout.dates.includes(target.date)
    &&layout.meal_types.some(meal=>meal.id===target.mealTypeId&&meal.menu_id===target.menuId)
    &&(criteria.selected_dates!=null ? criteria.selected_dates.includes(target.date)
      : (!criteria.start_date||target.date>=criteria.start_date)&&(!criteria.end_date||target.date<=criteria.end_date))
}

// Uses the existing draft saver. This orchestrates only entry, never confirm/reopen/sync.
export async function prepareAdjustmentMealEdit(options:{detail:OrderingAdjustmentDetail;target:AdjustmentMealTarget;layout:MenuAggregate|undefined;dirty:boolean;invalid:boolean;saveBlocked:boolean;sourceUnverified:boolean;save:()=>Promise<OrderingAdjustmentDetail|null>;refresh:()=>Promise<OrderingAdjustmentDetail>}) {
  const {detail,target,layout}=options
  if(!validAdjustmentMealTarget(detail,target,layout))throw new Error('目前狀態、來源範圍或採購鎖定不允許編輯本餐。')
  if(options.dirty){
    if(detail.stale||options.sourceUnverified||options.saveBlocked)throw new Error('來源已變更或版本有衝突，不能自動儲存舊來源輸入。請先處理未儲存修改，再同步或重新載入。')
    if(options.invalid)throw new Error('請先修正格式不正確的叫貨數量，再編輯本餐。')
    if(!await options.save())return null
  }else if(options.saveBlocked&&!detail.stale&&!options.sourceUnverified){
    throw new Error('工作表有版本衝突，請先重新載入後再編輯本餐。')
  }
  const current=await options.refresh()
  if(!validAdjustmentMealTarget(current,target,layout))throw new Error('工作表已確認、取消、被採購鎖定或來源範圍已改變，不能開啟編輯。請重新載入。')
  return current
}

// This is a permission/scope check, NOT another source diff or quantity calculator.
// Backend confirmation flags always win, including flags on unadjusted removals
// and additions. Incomplete metadata fails closed to the existing review dialog.
export function canAutoApplyMealSync(preview:OrderingAdjustmentSyncPreview,detail:OrderingAdjustmentDetail,target:AdjustmentMealTarget,aggregate:MenuAggregate,hadPendingSource:boolean) {
  if(hadPendingSource||detail.status!=='draft'||detail.purchase_locked!==false
    ||preview.sheet_id!==detail.id||preview.status!=='draft'||preview.lock_version!==detail.lock_version
    ||preview.saved_source_fingerprint!==detail.source_fingerprint||preview.changed!==true
    ||!/^[0-9a-f]{64}$/.test(preview.preview_source_fingerprint)||aggregate.menu.id!==target.menuId)return false
  const sections=['added_dishes','removed_dishes','possible_dish_replacements','added_ingredients','removed_ingredients','line_changes','unit_conflicts'] as const
  if(sections.some(key=>!Array.isArray(preview[key])))return false
  const counts={added_dishes:preview.added_dishes.length,removed_dishes:preview.removed_dishes.length,
    possible_dish_replacements:preview.possible_dish_replacements.length,added_ingredients:preview.added_ingredients.length,
    removed_ingredients:preview.removed_ingredients.length,changed_lines:preview.line_changes.length,unit_conflicts:preview.unit_conflicts.length}
  if(!preview.summary||Object.entries(counts).some(([key,count])=>preview.summary[key]!==count))return false
  if(sections.filter(key=>key!=='line_changes').some(key=>preview[key].length>0)||preview.line_changes.length===0)return false
  const slot=aggregate.slots.find(slot=>slot.menu_date===target.date&&slot.menu_meal_type_id===target.mealTypeId)
  if(!slot)return false
  // Line-change snapshots do not expose the LIVE date/meal. A positional
  // change could therefore be a concurrent move outside this meal, not merely
  // our own column/order edit. Only explicit review can authorize that case.
  const knownChanges=new Set(['dish_name_changed','ingredient_name_changed','diner_count_changed','reference_quantity_changed','unit_changed','source_metadata_changed'])
  const keys=new Set<string>()
  return preview.line_changes.every(change=>{
    const old=change.previous,next=change.current,key=change.source_line_key
    if(!key||keys.has(key)||!old||!next||change.requires_confirmation!==false||change.preserves_adjustment!==true
      ||!Array.isArray(change.change_types)||!change.change_types.length||change.change_types.some(type=>!knownChanges.has(type)))return false
    keys.add(key)
    const line=detail.lines.find(line=>line.id===old.line_id&&line.source_line_key===key)
    if(!line||old.source_line_key!==key||next.source_line_key!==key
      ||line.source_menu_id!==target.menuId||line.requirement_date!==target.date||line.source_meal_type_id!==target.mealTypeId)return false
    const identity=['source_menu_dish_id','source_dish_id','source_dish_ingredient_id','source_ingredient_id'] as const
    if(identity.some(field=>!line[field]||old[field]!==line[field]||next[field]!==line[field]))return false
    return slot.dishes.some(dish=>dish.id===line.source_menu_dish_id&&dish.dish_id===line.source_dish_id)
  })
}

export interface AdjustmentScrollPosition {left:number;top:number;pageX:number;pageY:number}
type Viewport=Pick<Window,'scrollX'|'scrollY'|'scrollTo'>
export function captureAdjustmentScroll(root:ParentNode|null,viewport:Viewport|undefined=typeof window==='undefined'?undefined:window):AdjustmentScrollPosition|null {
  const matrix=root?.querySelector<HTMLElement>('.ordering-adjustment-matrix')
  return matrix&&viewport?{left:matrix.scrollLeft,top:matrix.scrollTop,pageX:viewport.scrollX,pageY:viewport.scrollY}:null
}
export function restoreAdjustmentScroll(root:ParentNode|null,position:AdjustmentScrollPosition|null,viewport:Viewport|undefined=typeof window==='undefined'?undefined:window) {
  const matrix=root?.querySelector<HTMLElement>('.ordering-adjustment-matrix')
  if(!matrix||!position||!viewport)return
  // Native clamping keeps the viewport within the new matrix when rows disappear.
  matrix.scrollLeft=position.left;matrix.scrollTop=position.top
  viewport.scrollTo(position.pageX,position.pageY)
}
