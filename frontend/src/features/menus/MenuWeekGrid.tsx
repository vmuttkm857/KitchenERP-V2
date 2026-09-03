import { MealType, MealTypeColumn, MenuSlot } from './types'
import { mealGridRows } from './menuGridRows'

interface Props {
  dates: string[]
  meals: MealType[]
  columns: MealTypeColumn[]
  selectedKey: string | null
  slotFor: (date: string, meal: MealType) => MenuSlot
  onSelect: (date: string, meal: MealType) => void
  onEditColumns: (meal: MealType) => void
}

function dateLabel(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString('zh-TW', {
    month: 'numeric', day: 'numeric', weekday: 'short',
  })
}

export function MenuWeekGrid({ dates, meals, columns, selectedKey, slotFor, onSelect, onEditColumns }: Props) {
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
          return <td className={`meal-cell${selectedKey === cellKey ? ' is-selected' : ''}`} key={date}>
            <button className="meal-cell-button" onClick={() => onSelect(date, meal)} aria-label={`編輯 ${date} ${meal.name}`} aria-pressed={selectedKey === cellKey}>
              {dish?<div className="cell-dish"><strong title={dish.dish_name}>{dish.dish_name}</strong><span>{dish.diner_count} 人</span></div>:rowIndex===0&&slot.dishes.length===0?<span className="cell-empty">＋ 新增菜色</span>:null}
              {rowIndex===0&&slot.notes&&<small className="cell-note">本餐有備註</small>}
            </button>
          </td>
        })}
      </tr>)})}</tbody>
    </table>
  </div>
}
