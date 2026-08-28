import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { Dish, DishesPage } from '../features/dishes/DishesPage'
import { IngredientsPage } from '../features/ingredients/IngredientsPage'
import { RecipeEditor } from '../features/recipes/RecipeEditor'
import { SuppliersPage } from '../features/suppliers/SuppliersPage'

export function App() {
  const { user, isLoading, logout } = useAuth()
  const [page, setPage] = useState<'categories' | 'suppliers' | 'ingredients' | 'dishes' | 'recipe'>('categories')
  const [recipeDish, setRecipeDish] = useState<Dish | null>(null)

  if (isLoading) return <main className="shell"><p>載入中…</p></main>
  if (!user) return <LoginPage />

  return (
    <main className="app-shell">
      <header className="app-header"><div><p className="eyebrow">KitchenERP V2</p><strong>已登入：{user.display_name}</strong></div><button type="button" onClick={() => void logout()}>登出</button></header>
      <nav className="app-nav"><button onClick={() => setPage('categories')}>分類</button><button onClick={() => setPage('suppliers')}>供應商</button><button onClick={() => setPage('ingredients')}>食材</button><button onClick={() => setPage('dishes')}>菜色與配方</button></nav>
      <div className="workspace">{page === 'categories' && <CategoriesPage />}{page === 'suppliers' && <SuppliersPage />}{page === 'ingredients' && <IngredientsPage />}{page === 'dishes' && <DishesPage onEditRecipe={dish => { setRecipeDish(dish); setPage('recipe') }} />}{page === 'recipe' && recipeDish && <RecipeEditor dish={recipeDish} onClose={() => setPage('dishes')} />}</div>
    </main>
  )
}
