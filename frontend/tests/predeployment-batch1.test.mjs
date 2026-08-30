import assert from 'node:assert/strict'
import test from 'node:test'

import { attemptNavigation, confirmNavigation, shouldBlockNavigation } from '../src/app/navigationPolicy.ts'
import { buildListQuery, dateRangeError, menuCandidateDateParams, nextFilterPage, preserveSelected, RequestSequence, totalPages } from '../src/utils/listQuery.ts'

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

test('menu candidate date overlap and keyword are sent together', () => {
  const query = new URLSearchParams(buildListQuery({
    page: 1, pageSize: 20, search: '住院', ...menuCandidateDateParams('2026-08-20', '2026-08-25'),
  }))
  assert.equal(query.get('search'), '住院')
  assert.equal(query.get('start_date'), '2026-08-20')
  assert.equal(query.get('end_date'), '2026-08-25')
  assert.equal(nextFilterPage(), 1)
})

test('menu candidate dates support empty and one-sided searches', () => {
  assert.deepEqual(menuCandidateDateParams('', ''), { startDate: undefined, endDate: undefined })
  assert.deepEqual(menuCandidateDateParams('2026-08-20', ''), { startDate: '2026-08-20', endDate: undefined })
  assert.deepEqual(menuCandidateDateParams('', '2026-08-25'), { startDate: undefined, endDate: '2026-08-25' })
  assert.equal(dateRangeError('2026-08-26', '2026-08-25'), '開始日期不可晚於結束日期。')
})

test('candidate filtering stays separate from calculation and work dates', () => {
  const candidateDates = menuCandidateDateParams('2026-08-01', '2026-08-31')
  const calculationDates = { start_date: '2026-08-10', end_date: '2026-08-12' }
  const workDates = { start_date: '2026-08-15', end_date: '2026-08-16' }
  assert.deepEqual(candidateDates, { startDate: '2026-08-01', endDate: '2026-08-31' })
  assert.deepEqual(calculationDates, { start_date: '2026-08-10', end_date: '2026-08-12' })
  assert.deepEqual(workDates, { start_date: '2026-08-15', end_date: '2026-08-16' })
})

test('menu copy date query remains compatible with shared candidate parameters', () => {
  const query = new URLSearchParams(buildListQuery({
    page: 2, pageSize: 20, active: 'true', search: '來源', ...menuCandidateDateParams('2026-10-01', '2026-10-31'),
  }))
  assert.deepEqual(Object.fromEntries(query), {
    page: '2', page_size: '20', search: '來源', active: 'true', start_date: '2026-10-01', end_date: '2026-10-31',
  })
})
