import assert from 'node:assert/strict'
import test from 'node:test'

import { buildListQuery,nextFilterPage } from '../src/utils/listQuery.ts'
import { normalizeSupplierValues } from '../src/features/suppliers/supplierForm.ts'
import { isSupplierReorderEnabled,moveSupplierId,performSupplierReorder } from '../src/features/suppliers/supplierOrdering.ts'

test('supplier list query keeps search status and server-side pagination together',()=>{
  const query=new URLSearchParams(buildListQuery({page:3,pageSize:50,search:'  甲供應商  ',active:'true'}))
  assert.deepEqual(Object.fromEntries(query),{page:'3',page_size:'50',search:'甲供應商',active:'true'})
  assert.equal(nextFilterPage(),1)
})

test('supplier move disables global first up and global last down',()=>{
  const ids=['a','b','c']
  assert.equal(moveSupplierId(ids,'a','up'),ids)
  assert.equal(moveSupplierId(ids,'c','down'),ids)
  assert.deepEqual(moveSupplierId(ids,'b','up'),['b','a','c'])
  assert.deepEqual(moveSupplierId(ids,'b','down'),['a','c','b'])
})

test('supplier reorder is disabled while search or status filter is active',()=>{
  assert.equal(isSupplierReorderEnabled('',''),true)
  assert.equal(isSupplierReorderEnabled('供應商',''),false)
  assert.equal(isSupplierReorderEnabled('','true'),false)
})

test('supplier create and edit field mapping preserves contact address notes and status',()=>{
  assert.deepEqual(normalizeSupplierValues({
    code:' SUP-1 ',name:' 供應商 ',contact_person:' 王小姐 ',phone:' ',address:' 台北市 ',notes:' 下午送貨 ',is_active:false,
  }),{
    code:'SUP-1',name:'供應商',contact_person:'王小姐',phone:null,address:'台北市',notes:'下午送貨',is_active:false,
  })
})

test('successful supplier reorder submits the full order then reloads',async()=>{
  const calls=[]
  const reordered=await performSupplierReorder(['a','b','c'],'b','up',async ids=>calls.push(['submit',...ids]),async()=>{calls.push(['reload'])})
  assert.deepEqual(reordered,['b','a','c'])
  assert.deepEqual(calls,[['submit','b','a','c'],['reload']])
})

test('failed supplier reorder does not reload and preserves an application error path',async()=>{
  let reloads=0
  await assert.rejects(()=>performSupplierReorder(['a','b'],'b','up',async()=>{throw new Error('failed')},async()=>{reloads+=1}),/failed/)
  assert.equal(reloads,0)
})
