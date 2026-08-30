import assert from 'node:assert/strict'
import test from 'node:test'

import { attemptNavigation, confirmNavigation, shouldBlockNavigation } from '../src/app/navigationPolicy.ts'
import { buildListQuery, nextFilterPage, preserveSelected, RequestSequence, totalPages } from '../src/utils/listQuery.ts'

test('dirty editor blocks navigation until the application dialog confirms it', () => {
  let navigations = 0
  const navigate = () => { navigations += 1 }

  assert.equal(shouldBlockNavigation(true), true)
  assert.equal(attemptNavigation(true, navigate), false)
  assert.equal(navigations, 0)
  confirmNavigation(navigate)
  assert.equal(navigations, 1)
  assert.equal(attemptNavigation(false, navigate), true)
  assert.equal(navigations, 2)
})

test('list query includes server-side filters and pagination', () => {
  const query = new URLSearchParams(buildListQuery({
    page: 3, pageSize: 50, search: '  牛肉  ', active: 'true', categoryId: 'cat-1',
    supplierId: 'supplier-1', startDate: '2026-08-01', endDate: '2026-08-31',
  }))
  assert.deepEqual(Object.fromEntries(query), {
    page: '3', page_size: '50', search: '牛肉', active: 'true', category_id: 'cat-1',
    supplier_id: 'supplier-1', start_date: '2026-08-01', end_date: '2026-08-31',
  })
  assert.equal(nextFilterPage(), 1)
  assert.equal(totalPages(101, 50), 3)
})

test('stale responses cannot replace the latest request', () => {
  const requests = new RequestSequence()
  const oldRequest = requests.next()
  const latestRequest = requests.next()
  assert.equal(requests.isCurrent(oldRequest), false)
  assert.equal(requests.isCurrent(latestRequest), true)
})

test('menu candidate pages preserve menus already selected by the user', () => {
  const selected = new Map([['selected', { id: 'selected', name: '已選菜單' }]])
  const visible = preserveSelected([{ id: 'new', name: '搜尋結果' }], selected)
  assert.deepEqual(visible.map(item => item.id), ['selected', 'new'])
})
