import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { Dish, DishesPage } from '../features/dishes/DishesPage'
import { IngredientsPage } from '../features/ingredients/IngredientsPage'
import { MenuEditor } from '../features/menus/MenuEditor'
import { MenusPage } from '../features/menus/MenusPage'
import { Menu } from '../features/menus/types'
import { RecipeEditor } from '../features/recipes/RecipeEditor'
import { RequirementsPage } from '../features/requirements/RequirementsPage'
import { SuppliersPage } from '../features/suppliers/SuppliersPage'
import { SnapshotsPage } from '../features/snapshots/SnapshotsPage'
import { PurchasesPage } from '../features/purchases/PurchasesPage'

export function App() {
  const { user, isLoading, logout } = useAuth()
  const [page, setPage] = useState<'categories' | 'suppliers' | 'ingredients' | 'dishes' | 'recipe' | 'menus' | 'menu-editor' | 'requirements' | 'snapshots' | 'purchases'>('categories')
  const [recipeDish, setRecipeDish] = useState<Dish | null>(null)
  const [editingMenu, setEditingMenu] = useState<Menu | null>(null)
  const [purchaseId, setPurchaseId] = useState<string | null>(null)

  if (isLoading) return <main className="shell"><p>載入中…</p></main>
  if (!user) return <LoginPage />

  return (
    <main className="app-shell">
      <header className="app-header"><div><p className="eyebrow">KitchenERP V2</p><strong>已登入：{user.display_name}</strong></div><button type="button" onClick={() => void logout()}>登出</button></header>
      <nav className="app-nav"><button onClick={() => setPage('categories')}>分類</button><button onClick={() => setPage('suppliers')}>供應商</button><button onClick={() => setPage('ingredients')}>食材</button><button onClick={() => setPage('dishes')}>菜色與配方</button><button onClick={() => setPage('menus')}>菜單</button><button onClick={() => setPage('requirements')}>需求量預覽</button><button onClick={() => setPage('snapshots')}>固定需求快照</button><button onClick={() => setPage('purchases')}>正式採購</button></nav>
      <div className="workspace">{page === 'categories' && <CategoriesPage />}{page === 'suppliers' && <SuppliersPage />}{page === 'ingredients' && <IngredientsPage />}{page === 'dishes' && <DishesPage onEditRecipe={dish => { setRecipeDish(dish); setPage('recipe') }} />}{page === 'recipe' && recipeDish && <RecipeEditor dish={recipeDish} onClose={() => setPage('dishes')} />}{page === 'menus' && <MenusPage onOpen={menu => { setEditingMenu(menu); setPage('menu-editor') }} />}{page === 'menu-editor' && editingMenu && <MenuEditor menu={editingMenu} onClose={() => setPage('menus')} />}{page === 'requirements' && <RequirementsPage />}{page === 'snapshots' && <SnapshotsPage onPurchase={id=>{setPurchaseId(id);setPage('purchases')}}/>}{page === 'purchases' && <PurchasesPage initialId={purchaseId}/>}</div>
    </main>
  )
}
