import { MealType, MenuSlot } from './types'

interface Props {
  dates: string[]
  meals: MealType[]
  selectedKey: string | null
  slotFor: (date: string, meal: MealType) => MenuSlot
  onSelect: (date: string, meal: MealType) => void
}

function dateLabel(date: string) {
  return new Date(`${date}T00:00:00`).toLocaleDateString('zh-TW', {
    month: 'numeric', day: 'numeric', weekday: 'short',
  })
}

export function MenuWeekGrid({ dates, meals, selectedKey, slotFor, onSelect }: Props) {
  return <div className="menu-matrix" aria-label="一週菜單表格">
    <table>
      <thead><tr><th className="sticky-col">餐別</th>{dates.map(date => <th key={date}><span>{dateLabel(date)}</span><small>{date}</small></th>)}</tr></thead>
      <tbody>{meals.map(meal => <tr key={meal.id}>
        <th className="sticky-col">{meal.name}{!meal.is_active && <small>已停用（歷史）</small>}</th>
        {dates.map(date => {
          const slot = slotFor(date, meal)
          const cellKey = `${date}:${meal.id}`
          return <td className={`meal-cell${selectedKey === cellKey ? ' is-selected' : ''}`} key={date}>
            <button className="meal-cell-button" onClick={() => onSelect(date, meal)} aria-label={`編輯 ${date} ${meal.name}`} aria-pressed={selectedKey === cellKey}>
              {slot.dishes.length ? <div className="cell-dishes">{slot.dishes.map(dish => <div className="cell-dish" key={dish.id ?? dish.dish_id}><strong>{dish.dish_name}</strong><span>{dish.diner_count} 人</span></div>)}</div> : <span className="cell-empty">＋ 新增菜色</span>}
              {slot.notes && <small className="cell-note">本餐有備註</small>}
            </button>
          </td>
        })}
      </tr>)}</tbody>
    </table>
  </div>
}
