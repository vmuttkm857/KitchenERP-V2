import { DragEvent, useEffect, useRef, useState } from 'react'
import { MealType, MealTypeColumn, MenuSlot } from './types'
import { mealGridRows } from './menuGridRows'
import { canInsertMenuDish, MenuDishInsertTarget } from './menuDrag'

interface Props {
  dates: string[]
  meals: MealType[]
  columns: MealTypeColumn[]
  selectedKey: string | null
  slotFor: (date: string, meal: MealType) => MenuSlot
  onSelect: (date: string, meal: MealType) => void
  onEditColumns: (meal: MealType) => void
  onMoveDish: (sourceMenuDishId:string,target:MenuDishInsertTarget) => Promise<void>
  movingDish: boolean
}

function dateLabel(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString('zh-TW', {
    month: 'numeric', day: 'numeric', weekday: 'short',
  })
}

export function MenuWeekGrid({ dates, meals, columns, selectedKey, slotFor, onSelect, onEditColumns, onMoveDish, movingDish }: Props) {
  const [draggedDishId,setDraggedDishId]=useState<string|null>(null)
  const [dropTarget,setDropTarget]=useState<MenuDishInsertTarget|null>(null)
  const suppressClickUntil=useRef(0)
  const finishFrame=useRef<number|null>(null)
  useEffect(()=>()=>{if(finishFrame.current!==null)window.cancelAnimationFrame(finishFrame.current)},[])
  function startDrag(event:DragEvent,menuDishId:string){
    if(movingDish){event.preventDefault();return}
    setDraggedDishId(menuDishId);suppressClickUntil.current=Date.now()+300
    event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',menuDishId)
  }
  function finishDrag(){setDraggedDishId(null);setDropTarget(null);suppressClickUntil.current=Date.now()+300}
  function scheduleFinishDrag(){
    if(finishFrame.current!==null)window.cancelAnimationFrame(finishFrame.current)
    finishFrame.current=window.requestAnimationFrame(()=>{finishFrame.current=null;finishDrag()})
  }
  return <div className="menu-matrix" aria-label="一週菜單表格">
    <table>
      <thead><tr><th className="sticky-col">餐別</th><th className="menu-column-heading">菜單欄位</th>{dates.map(date => <th key={date}><span>{dateLabel(date)}</span><small>{date}</small></th>)}</tr></thead>
      <tbody>{meals.flatMap(meal => {
        const rows=mealGridRows(dates,meal,columns,slotFor)
        return rows.map((row,rowIndex)=><tr key={`${meal.id}:${rowIndex}`}>
        {rowIndex===0&&<th className="sticky-col" rowSpan={rows.length}>{meal.name}{!meal.is_active && <small>已停用（歷史）</small>}</th>}
        <th className="menu-column-cell"><button onClick={()=>onEditColumns(meal)} aria-label={`編輯 ${meal.name} 菜單欄位`}>{row.label}</button></th>
        {dates.map((date,dateIndex) => {
          const slot = slotFor(date,meal)
          const dish = row.dishes[dateIndex]
          const cellKey = `${date}:${meal.id}`
          const insertTarget=(insertIndex:number):MenuDishInsertTarget=>({
            targetDate:date,targetMealTypeId:meal.id,insertIndex,
            beforeMenuDishId:insertIndex>0?rows[insertIndex-1]?.dishes[dateIndex]?.id??null:null,
            afterMenuDishId:rows[insertIndex]?.dishes[dateIndex]?.id??null,
          })
          const activeTarget=dropTarget?.targetDate===date&&dropTarget.targetMealTypeId===meal.id?dropTarget:null
          const insertBefore=activeTarget?.insertIndex===rowIndex
          const insertAfter=activeTarget?.insertIndex===rowIndex+1
          return <td className={`meal-cell${selectedKey === cellKey ? ' is-selected' : ''}${insertBefore?' is-insert-before':''}${insertAfter?' is-insert-after':''}${draggedDishId&&dish?.id===draggedDishId?' is-drag-source':''}`} key={date}
            onDragOver={event=>{const bounds=event.currentTarget.getBoundingClientRect();const index=event.clientY<bounds.top+bounds.height/2?rowIndex:rowIndex+1;const target=insertTarget(index);if(canInsertMenuDish(draggedDishId,target,movingDish)){event.preventDefault();event.dataTransfer.dropEffect='move';setDropTarget(target)}}}
            onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node|null))setDropTarget(null)}}
            onDrop={event=>{event.preventDefault();event.stopPropagation();const bounds=event.currentTarget.getBoundingClientRect();const target=insertTarget(event.clientY<bounds.top+bounds.height/2?rowIndex:rowIndex+1);const sourceId=event.dataTransfer.getData('text/plain')||draggedDishId;if(!canInsertMenuDish(sourceId,target,movingDish))return;if(sourceId)void onMoveDish(sourceId,target);scheduleFinishDrag()}}>
            <button className="meal-cell-button" onClick={() => {if(Date.now()>=suppressClickUntil.current)onSelect(date, meal)}} aria-label={`編輯 ${date} ${meal.name}`} aria-pressed={selectedKey === cellKey}>
              {dish?<div className="cell-dish" draggable={!movingDish} onDragStart={event=>dish.id&&startDrag(event,dish.id)} onDragEnd={scheduleFinishDrag} title="拖曳菜色以移動排序"><strong title={dish.dish_name}>{dish.dish_name}</strong><span>{dish.diner_count} 人</span></div>:rowIndex===0&&slot.dishes.length===0?<span className="cell-empty">＋ 新增菜色</span>:null}
              {rowIndex===0&&slot.notes&&<small className="cell-note">本餐有備註</small>}
            </button>
          </td>
        })}
      </tr>)})}</tbody>
    </table>
  </div>
}
