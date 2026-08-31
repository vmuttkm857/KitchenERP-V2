import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const app=readFileSync(new URL('../src/app/App.tsx',import.meta.url),'utf8')
const users=readFileSync(new URL('../src/features/users/UsersPage.tsx',import.meta.url),'utf8')
const audit=readFileSync(new URL('../src/features/audit/AuditLogsPage.tsx',import.meta.url),'utf8')

test('system management navigation is rendered only for administrators',()=>{
  assert.match(app,/user\.role==='admin'\?\[\.\.\.businessGroups,systemGroup\]:businessGroups/)
  assert.match(app,/使用者管理/)
  assert.match(app,/操作紀錄/)
  assert.match(app,/page==='users'&&user\.role==='admin'/)
  assert.match(app,/page==='audit'&&user\.role==='admin'/)
})

test('users page provides server-side list filters and formal application dialogs',()=>{
  assert.match(users,/\/users\?\$\{query\}/)
  assert.match(users,/query\.set\('search'/)
  assert.match(users,/query\.set\('active'/)
  assert.match(users,/query\.set\('role'/)
  assert.match(users,/新增使用者/)
  assert.match(users,/重設使用者密碼/)
  assert.match(users,/停用使用者/)
  assert.match(users,/恢復使用者/)
  assert.doesNotMatch(users,/window\.(alert|confirm|prompt)/)
})

test('password changes use password inputs and never render credential internals',()=>{
  assert.match(users,/type="password"/)
  assert.match(users,/目前管理員密碼/)
  assert.match(users,/所有登入工作階段都會撤銷/)
  assert.doesNotMatch(users,/password_hash|refresh_token|access_token/)
})

test('audit page uses server-side pagination and filters with a detail dialog',()=>{
  for(const value of ["keyword","action","entity_type","date_from","date_to"]){
    assert.match(audit,new RegExp(`query\\.set\\('${value}'`))
  }
  assert.match(audit,/PaginationControls/)
  assert.match(audit,/修改前/)
  assert.match(audit,/修改後/)
  assert.match(audit,/role="dialog"/)
  assert.doesNotMatch(audit,/password_hash|refresh_token|access_token/)
})

test('self password change logs the user out after all refresh sessions are revoked',()=>{
  assert.match(app,/\/users\/me\/change-password/)
  assert.match(app,/await logout\(\)/)
})
