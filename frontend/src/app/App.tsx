import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { IngredientsPage } from '../features/ingredients/IngredientsPage'
import { SuppliersPage } from '../features/suppliers/SuppliersPage'

export function App() {
  const { user, isLoading, logout } = useAuth()
  const [page, setPage] = useState<'categories' | 'suppliers' | 'ingredients'>('categories')

  if (isLoading) return <main className="shell"><p>載入中…</p></main>
  if (!user) return <LoginPage />

  return (
    <main className="app-shell">
      <header className="app-header"><div><p className="eyebrow">KitchenERP V2</p><strong>已登入：{user.display_name}</strong></div><button type="button" onClick={() => void logout()}>登出</button></header>
      <nav className="app-nav"><button onClick={() => setPage('categories')}>分類</button><button onClick={() => setPage('suppliers')}>供應商</button><button onClick={() => setPage('ingredients')}>食材</button></nav>
      <div className="workspace">{page === 'categories' && <CategoriesPage />}{page === 'suppliers' && <SuppliersPage />}{page === 'ingredients' && <IngredientsPage />}</div>
    </main>
  )
}
