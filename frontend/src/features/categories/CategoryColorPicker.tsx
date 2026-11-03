import { DISH_BACKGROUND_COLORS } from './categoryDisplay.js'

export function CategoryColorPicker({ value, disabled, onChange }: { value: string | null; disabled: boolean; onChange: (value: string | null) => void }) {
  return <fieldset className="category-color-picker" disabled={disabled}>
    <legend>菜色背景顏色</legend>
    <div className="category-color-options">
      <button type="button" className="category-color-choice" aria-pressed={value === null} onClick={() => onChange(null)}>無顏色</button>
      {DISH_BACKGROUND_COLORS.map(color => <button type="button" key={color.value} className="category-color-choice" style={{ backgroundColor: color.value }} aria-label={color.name} aria-pressed={value?.toUpperCase() === color.value} onClick={() => onChange(color.value)}>{color.name}</button>)}
    </div>
    <div className="category-color-preview" style={{ backgroundColor: value ?? undefined }}><span>目前背景：{value ?? '中性（無顏色）'}</span></div>
  </fieldset>
}
