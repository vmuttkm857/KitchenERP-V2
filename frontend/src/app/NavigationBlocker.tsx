import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react'
import { attemptNavigation, confirmNavigation } from './navigationPolicy'

interface NavigationBlockerValue {
  requestNavigation: (action: () => void) => void
  setEditorDirty: (dirty: boolean) => void
}

const NavigationBlockerContext = createContext<NavigationBlockerValue | null>(null)

export function NavigationBlockerProvider({ children }: { children: ReactNode }) {
  const [dirty, setDirty] = useState(false)
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)
  const requestNavigation = useCallback((action: () => void) => {
    if (!attemptNavigation(dirty, action)) setPendingAction(() => action)
  }, [dirty])
  useEffect(() => {
    if (!dirty) return
    const block = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', block)
    return () => window.removeEventListener('beforeunload', block)
  }, [dirty])
  function leave() {
    const action = pendingAction
    setPendingAction(null); setDirty(false)
    confirmNavigation(action)
  }
  return <NavigationBlockerContext.Provider value={{ requestNavigation, setEditorDirty: setDirty }}>
    {children}
    {pendingAction && <div className="modal-backdrop"><section className="modal-panel danger-dialog" role="alertdialog" aria-modal="true" aria-labelledby="navigation-guard-title"><header><div><h2 id="navigation-guard-title">尚有未儲存的變更</h2><p>離開後，這些修改將不會保留。</p></div></header><footer><button autoFocus className="secondary" onClick={() => setPendingAction(null)}>留在此頁</button><button className="secondary-danger" onClick={leave}>放棄修改並離開</button></footer></section></div>}
  </NavigationBlockerContext.Provider>
}

export function useNavigationBlocker() {
  const value = useContext(NavigationBlockerContext)
  if (!value) throw new Error('NavigationBlockerProvider is missing')
  return value
}

export function useEditorDirty(dirty: boolean) {
  const { setEditorDirty } = useNavigationBlocker()
  useEffect(() => { setEditorDirty(dirty); return () => setEditorDirty(false) }, [dirty, setEditorDirty])
}
