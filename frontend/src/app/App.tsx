import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { LoadingState } from '../components/ui/Page'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { Dish, DishesPage } from '../features/dishes/DishesPage'
import { IngredientsPage } from '../features/ingredients/IngredientsPage'
import { KitchenOperationsPage } from '../features/kitchen_operations/KitchenOperationsPage'
import { MenuEditor } from '../features/menus/MenuEditor'
import { MenusPage } from '../features/menus/MenusPage'
import { Menu } from '../features/menus/types'
import { PurchasesPage } from '../features/purchases/PurchasesPage'
import { RecipeEditor } from '../features/recipes/RecipeEditor'
import { RequirementsPage } from '../features/requirements/RequirementsPage'
import { SnapshotsPage } from '../features/snapshots/SnapshotsPage'
import { SuppliersPage } from '../features/suppliers/SuppliersPage'

type Page='categories'|'suppliers'|'ingredients'|'dishes'|'recipe'|'menus'|'menu-editor'|'requirements'|'snapshots'|'purchases'|'kitchen'
const groups=[
  {label:'主檔管理',items:[['categories','分類'],['suppliers','供應商'],['ingredients','食材'],['dishes','菜色／配方']]},
  {label:'菜單',items:[['menus','菜單管理'],['kitchen','廚房作業']]},
  {label:'需求／採購',items:[['requirements','食材需求'],['snapshots','固定需求快照'],['purchases','正式採購']]},
] as const

export function App(){
  const {user,isLoading,logout}=useAuth();const [page,setPage]=useState<Page>('categories');const [navOpen,setNavOpen]=useState(false)
  const [recipeDish,setRecipeDish]=useState<Dish|null>(null);const [editingMenu,setEditingMenu]=useState<Menu|null>(null);const [purchaseId,setPurchaseId]=useState<string|null>(null)
  if(isLoading)return <main className="shell"><LoadingState label="系統載入中…"/></main>
  if(!user)return <LoginPage/>
  function navigate(next:Page){setPage(next);setNavOpen(false)}
  return <div className="app-layout">
    <header className="topbar"><button className="nav-toggle secondary" aria-label="開啟導覽" aria-expanded={navOpen} onClick={()=>setNavOpen(v=>!v)}>選單</button><div><span className="brand">KitchenERP</span><small>廚房營運管理</small></div><div className="account"><span>{user.display_name}</span><button className="secondary" onClick={()=>void logout()}>登出</button></div></header>
    <aside className={`sidebar ${navOpen?'is-open':''}`} aria-label="主要導覽">{groups.map(group=><section className="nav-group" key={group.label}><h2>{group.label}</h2>{group.items.map(([id,label])=><button key={id} className={page===id?'active':''} aria-current={page===id?'page':undefined} onClick={()=>navigate(id)}>{label}</button>)}</section>)}</aside>
    {navOpen&&<button className="nav-backdrop" aria-label="關閉導覽" onClick={()=>setNavOpen(false)}/>}
    <main className="workspace" id="main-content">
      {page==='categories'&&<CategoriesPage/>}{page==='suppliers'&&<SuppliersPage/>}{page==='ingredients'&&<IngredientsPage/>}
      {page==='dishes'&&<DishesPage onEditRecipe={dish=>{setRecipeDish(dish);navigate('recipe')}}/>}{page==='recipe'&&recipeDish&&<RecipeEditor dish={recipeDish} onClose={()=>navigate('dishes')}/>}
      {page==='menus'&&<MenusPage onOpen={menu=>{setEditingMenu(menu);navigate('menu-editor')}}/>}{page==='menu-editor'&&editingMenu&&<MenuEditor menu={editingMenu} onClose={()=>navigate('menus')}/>}
      {page==='kitchen'&&<KitchenOperationsPage/>}{page==='requirements'&&<RequirementsPage/>}{page==='snapshots'&&<SnapshotsPage onPurchase={id=>{setPurchaseId(id);navigate('purchases')}}/>}{page==='purchases'&&<PurchasesPage initialId={purchaseId}/>}
    </main>
  </div>
}
