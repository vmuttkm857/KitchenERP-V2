import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { apiRequest } from '../../api/client'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { Feedback, LoadingState } from '../../components/ui/Page'
import { MenuEditorPanel } from './MenuEditorPanel'
import { MealEditorController } from './mealEditorController'
import type { MenuAggregate, MenuMealAdjustmentContext } from './types'

export interface MenuMealEditorDialogProps {
  menuId: string
  date: string
  mealTypeId: string
  onSaved: (aggregate: MenuAggregate, result: { changed: boolean }) => void
  onClose: () => void
  orderingAdjustmentContext?: MenuMealAdjustmentContext
}

type Confirmation = { kind: 'discard' } | { kind: 'reload' } | { kind: 'remove'; index: number }

export function MenuMealEditorDialog(props: MenuMealEditorDialogProps) {
  return <MealEditorSession key={`${props.menuId}:${props.date}:${props.mealTypeId}`} {...props}/>
}

function MealEditorSession({ menuId, date, mealTypeId, onSaved, onClose, orderingAdjustmentContext }: MenuMealEditorDialogProps) {
  const controller = useMemo(() => new MealEditorController(menuId, date, mealTypeId, apiRequest, orderingAdjustmentContext), [menuId, date, mealTypeId, orderingAdjustmentContext?.sheet_id, orderingAdjustmentContext?.lock_version])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  const clearDirty = useEditorDirty(state.dirty)
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [page, setPage] = useState(1)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const opener = useRef<HTMLElement | null>(document.activeElement as HTMLElement | null)
  const confirmationRef = useRef<HTMLElement>(null)
  const busy = state.saving || state.loading
  const meal = state.aggregate?.meal_types.find(item => item.id === mealTypeId)

  useEffect(() => {
    void controller.load()
    return () => { controller.dispose(); opener.current?.focus({ preventScroll: true }) }
  }, [controller])
  useEffect(() => {
    if (!state.loading && state.slot) searchInputRef.current?.focus()
  }, [state.loading, state.slot === null])
  useEffect(() => {
    const timer = window.setTimeout(() => { void controller.search(search, categoryId, page) }, 250)
    return () => window.clearTimeout(timer)
  }, [controller, search, categoryId, page])

  function close() { clearDirty(); onClose() }
  function requestClose() {
    if (busy) return
    if (state.dirty) setConfirmation({ kind: 'discard' })
    else close()
  }
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      if (confirmation) { setConfirmation(null); searchInputRef.current?.focus() }
      else requestClose()
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  })

  async function save() {
    const changed = controller.getSnapshot().dirty
    const aggregate = await controller.save()
    if (aggregate) { clearDirty(); onSaved(aggregate, { changed }); onClose() }
  }
  function reload() {
    if (state.dirty) setConfirmation({ kind: 'reload' })
    else void controller.load()
  }
  function confirm() {
    if (!confirmation || busy) return
    if (confirmation.kind === 'discard') close()
    else if (confirmation.kind === 'reload') void controller.load()
    else { controller.remove(confirmation.index); searchInputRef.current?.focus() }
    setConfirmation(null)
  }
  const description = confirmation?.kind === 'discard' ? '尚未儲存的本餐內容將會遺失。'
    : confirmation?.kind === 'reload' ? '重新載入會放棄本餐尚未儲存的輸入，取得最新餐次及版本後可重新編輯。'
    : confirmation?.kind === 'remove' ? `只會從本餐移除「${state.slot?.dishes[confirmation.index]?.dish_name ?? '此菜色'}」，不會刪除菜色主檔。` : ''

  return <>
    {state.slot && meal ? <MenuEditorPanel date={date} meal={meal} columns={state.aggregate!.meal_type_columns} slot={state.slot}
      search={search} categoryId={categoryId} categories={state.categories} results={state.results} searchTotal={state.total} searchPage={page} searchLoading={state.searchLoading}
      searchInputRef={searchInputRef} onClose={requestClose} onSave={save} saving={busy} blocked={state.conflict}
      saveError={[state.error, state.searchError].filter(Boolean).join(' ')} onReload={state.contextBlocked?undefined:reload}
      onSlotNotes={notes => controller.change({ ...state.slot!, notes })} onDishChange={(index, changes) => controller.updateDish(index, changes)}
      onMove={(index, direction) => controller.move(index, direction)} onRemove={index => setConfirmation({ kind: 'remove', index })}
      onSearch={value => { setSearch(value); setPage(1) }} onCategory={value => { setCategoryId(value); setPage(1) }} onSearchPage={setPage} onAdd={dish => controller.add(dish)}/>
      : <div className="modal-backdrop"><section className="modal-panel" role="dialog" aria-modal="true" aria-label="編輯餐次">
        <h2>編輯餐次</h2>{state.loading ? <LoadingState label="餐次載入中…"/> : <Feedback type="error">{state.error}</Feedback>}
        <footer><button autoFocus className="secondary" disabled={state.saving} onClick={close}>取消</button><button disabled={busy} onClick={() => void controller.load()}>重新載入</button></footer>
      </section></div>}
    {confirmation && <div className="modal-backdrop"><section ref={confirmationRef} className="modal-panel danger-dialog" role="alertdialog" aria-modal="true" aria-labelledby="meal-confirm-title"
      onKeyDown={event => {
        if (event.key !== 'Tab') return
        const controls = confirmationRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
        if (!controls?.length) return
        const first = controls[0], last = controls[controls.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }}>
      <header><div><h2 id="meal-confirm-title">{confirmation.kind === 'discard' ? '放棄本餐修改？' : confirmation.kind === 'reload' ? '重新載入最新餐次？' : '移除菜色？'}</h2><p>{description}</p></div></header>
      <footer><button autoFocus className="secondary" onClick={() => { setConfirmation(null); searchInputRef.current?.focus() }}>取消</button><button className="secondary-danger" onClick={confirm}>{confirmation.kind === 'reload' ? '放棄修改並重新載入' : confirmation.kind === 'discard' ? '放棄修改' : '確認移除'}</button></footer>
    </section></div>}
  </>
}
