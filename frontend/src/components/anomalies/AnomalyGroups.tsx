import type { AnomalyGroup } from './anomalies'

function GroupSection({title,groups}:{title:string;groups:AnomalyGroup[]}){
  if(!groups.length)return null
  return <div className="anomaly-list anomaly-list-compact"><h3>{title} {groups.length}</h3><ul>{groups.map(group=><li className={group.severity} key={group.key}><strong>{group.title}</strong><p>{group.description}</p><small>影響 {group.count} 筆菜單內容</small></li>)}</ul></div>
}

export function AnomalyGroups({groups}:{groups:AnomalyGroup[]}){
  return <><GroupSection title="需要處理" groups={groups.filter(group=>group.severity==='error')}/><GroupSection title="提醒" groups={groups.filter(group=>group.severity==='warning')}/></>
}
