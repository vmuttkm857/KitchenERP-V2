import { ReactNode } from 'react'

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{description}</p></div>{actions&&<div className="page-actions">{actions}</div>}</header>
}

export function Feedback({ type, children }: { type: 'error'|'success'|'info'; children: ReactNode }) {
  return <div className={`feedback feedback-${type}`} role={type==='error'?'alert':'status'}>{children}</div>
}

export function LoadingState({ label='資料載入中…' }: { label?: string }) {
  return <div className="state-panel" role="status"><span className="spinner" aria-hidden="true"/>{label}</div>
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return <div className="state-panel empty-state"><strong>{title}</strong>{description&&<p>{description}</p>}</div>
}

export function StatusBadge({ active, activeLabel='啟用', inactiveLabel='停用' }: { active: boolean; activeLabel?: string; inactiveLabel?: string }) {
  return <span className={`status-badge ${active?'is-active':'is-inactive'}`}>{active?activeLabel:inactiveLabel}</span>
}

export function TableFrame({ children }: { children: ReactNode }) { return <div className="table-frame">{children}</div> }
