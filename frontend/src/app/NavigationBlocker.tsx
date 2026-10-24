import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { attemptNavigation, confirmNavigation } from './navigationPolicy'

interface NavigationBlockerValue {
  requestNavigation: (action: () => void) => void
  setEditorDirty: (dirty: boolean, owner?: symbol) => void
}

const NavigationBlockerContext = createContext<NavigationBlockerValue | null>(null)

export function NavigationBlockerProvider({ children }: { children: ReactNode }) {
  const [dirty, setDirty] = useState(false)
  const dirtyRef = useRef(false)
  const dirtyEditors = useRef(new Map<symbol | undefined, boolean>())
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)
  const setEditorDirty = useCallback((editorDirty: boolean, owner?: symbol) => {
    if (editorDirty) dirtyEditors.current.set(owner, true)
    else dirtyEditors.current.delete(owner)
    const value = dirtyEditors.current.size > 0
    dirtyRef.current = value
    setDirty(value)
  }, [])
  const requestNavigation = useCallback((action: () => void) => {
    if (!attemptNavigation(dirtyRef.current, action)) setPendingAction(() => action)
  }, [])
  useEffect(() => {
    if (!dirty) return
    const block = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', block)
    return () => window.removeEventListener('beforeunload', block)
  }, [dirty])
  function leave() {
    const action = pendingAction
    setPendingAction(null); dirtyEditors.current.clear(); setEditorDirty(false)
    confirmNavigation(action)
  }
  return <NavigationBlockerContext.Provider value={{ requestNavigation, setEditorDirty }}>
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
  const owner = useRef(Symbol('editor'))
  useEffect(() => { setEditorDirty(dirty, owner.current); return () => setEditorDirty(false, owner.current) }, [dirty, setEditorDirty])
  return useCallback(() => setEditorDirty(false, owner.current), [setEditorDirty])
}
