import assert from 'node:assert/strict'
import test from 'node:test'

import { buildListQuery, clearDateRange, dateRangeError, nextFilterPage, totalPages } from '../src/utils/listQuery.ts'

test('snapshot history query sends server-side date and pagination parameters', () => {
  const query = new URLSearchParams(buildListQuery({
    page: 2, pageSize: 50, startDate: '2026-08-01', endDate: '2026-08-31',
  }))
  assert.deepEqual(Object.fromEntries(query), {
    page: '2', page_size: '50', start_date: '2026-08-01', end_date: '2026-08-31',
  })
})

test('purchase history keeps status and keyword while adding date filters', () => {
  const query = new URLSearchParams(buildListQuery({
    page: 1, pageSize: 100, purchaseStatus: 'confirmed', search: 'PO-202608',
    startDate: '2026-08-01', endDate: '2026-08-31',
  }))
  assert.deepEqual(Object.fromEntries(query), {
    page: '1', page_size: '100', search: 'PO-202608', purchase_status: 'confirmed',
    start_date: '2026-08-01', end_date: '2026-08-31',
  })
})

test('date and page-size changes reset page and invalid ranges are blocked', () => {
  assert.equal(nextFilterPage(), 1)
  assert.equal(dateRangeError('2026-09-02', '2026-09-01'), '開始日期不可晚於結束日期。')
  assert.equal(dateRangeError('2026-09-01', '2026-09-01'), '')
})

test('clear dates returns an unrestricted range', () => {
  assert.deepEqual(clearDateRange(), { startDate: '', endDate: '' })
})

test('pagination metadata drives total page count', () => {
  const pagination = { page: 2, page_size: 25, total: 76 }
  assert.equal(totalPages(pagination.total, pagination.page_size), 4)
})
