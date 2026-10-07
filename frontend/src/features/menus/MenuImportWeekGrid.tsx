import type {MenuImportGridLine,MenuImportLayoutRow} from './menuImportTypes'
import {menuImportDates,menuImportGridRows,menuImportStatus} from './menuImportGrid'

const weekdays=['日','一','二','三','四','五','六']
const statusLabels={MATCHED:'已配對',MANUALLY_RESOLVED:'已人工確認',UNMATCHED:'找不到菜色',AMBIGUOUS:'多筆相符',INACTIVE_MATCH:'相符菜色已停用',EXCLUDED:'已排除'} as const
function dateLabel(value:string){const date=new Date(`${value}T00:00:00Z`);return `${Number(value.slice(5,7))}/${Number(value.slice(8,10))}（${weekdays[date.getUTCDay()]}）`}
function draftState(line:MenuImportGridLine){
  if('resolution_status'in line&&line.resolution_status==='EXCLUDED')return'excluded'
  if('duplicate_conflict'in line&&line.duplicate_conflict)return'duplicate'
  if(line.review_required)return'needs-review'
  return'normal'
}

export function MenuImportWeekGrid({startDate,endDate,layout,lines,onLine}:{startDate:string;endDate:string;layout:MenuImportLayoutRow[];lines:MenuImportGridLine[];onLine?:(line:MenuImportGridLine)=>void}){
  const dates=menuImportDates(startDate,endDate),rows=menuImportGridRows(lines,dates,layout)
  return <div className="menu-import-grid-wrap"><table className="menu-import-grid"><thead><tr><th>餐別</th><th>菜單欄位</th>{dates.map(date=><th key={date}>{dateLabel(date)}</th>)}</tr></thead><tbody>{rows.map((row,index)=>{
    const first=index===0||rows[index-1].mealName!==row.mealName
    const span=first?rows.slice(index).findIndex((candidate,offset)=>offset>0&&candidate.mealName!==row.mealName):-1
    const rowSpan=first?(span===-1?rows.length-index:span):0
    return <tr key={row.key} className={first?'meal-start':''}>{first&&<th rowSpan={rowSpan}>{row.mealName}</th>}<th>{row.columnName}</th>{row.cells.map((line,cellIndex)=><td key={dates[cellIndex]}>{line&&<button type="button" title={line.dish&&line.dish.name!==line.original_import_name?`Excel 原始名稱：${line.original_import_name}\n目前菜色：${line.dish.name}`:line.original_import_name} aria-label={`${line.dish?.name??line.original_import_name}，${draftState(line)==='normal'?'可編輯':statusLabels[menuImportStatus(line)]}`} className={`menu-import-cell ${draftState(line)}`} onClick={()=>onLine?.(line)} disabled={!onLine}>
      <span className="menu-import-dish-name">{line.dish?.name??line.original_import_name}</span><span className="menu-import-diner">{line.diner_count} 人</span>
      {draftState(line)==='excluded'&&<span className="menu-import-excluded-badge">已排除</span>}
      {draftState(line)==='duplicate'&&<><span className="menu-import-duplicate-badge">重複菜色</span><small>同一天同餐別已有相同菜色</small></>}
      {draftState(line)==='needs-review'&&<><span className="menu-import-review-badge">需確認</span><small>{statusLabels[menuImportStatus(line)]}</small></>}
      {draftState(line)==='normal'&&<span className="menu-import-edit-hint" aria-hidden="true">編輯</span>}
    </button>}</td>)}</tr>
  })}</tbody></table>{rows.length===0&&<p className="empty-state">此匯入沒有可顯示的菜色資料。</p>}</div>
}
