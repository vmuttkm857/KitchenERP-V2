import { useEffect, useState } from 'react'
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
import { NavigationBlockerProvider, useNavigationBlocker } from './NavigationBlocker'

type Page='categories'|'suppliers'|'ingredients'|'dishes'|'recipe'|'menus'|'menu-editor'|'requirements'|'snapshots'|'purchases'|'kitchen'
const groups=[
  {label:'主檔管理',items:[['categories','分類'],['suppliers','供應商'],['ingredients','食材'],['dishes','菜色／配方']]},
  {label:'菜單',items:[['menus','菜單管理'],['kitchen','廚房作業']]},
  {label:'需求／採購',items:[['requirements','食材需求'],['snapshots','固定需求快照'],['purchases','正式採購']]},
] as const

type NavPage=(typeof groups)[number]['items'][number][0]
const sidebarPreferenceKey='kitchenerp.sidebar.collapsed'

function NavIcon({page}:{page:NavPage}){
  const paths:Record<NavPage,string>={
    categories:'M4 5h6v6H4V5Zm10 0h6v6h-6V5ZM4 15h6v4H4v-4Zm10 0h6v4h-6v-4Z',
    suppliers:'M3 7h12v10H3V7Zm12 3h3l3 3v4h-6v-7ZM6 4h6v3H6V4Zm1 15a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
    ingredients:'M12 3c4 2 7 5 7 9a7 7 0 0 1-14 0c0-4 3-7 7-9Zm0 4v10m-4-6h8',
    dishes:'M4 12a8 8 0 0 1 16 0H4Zm-1 3h18M12 4V2',
    menus:'M5 3h14v18H5V3Zm4 0v4m6-4v4M8 11h8m-8 4h8',
    kitchen:'M5 3v7a3 3 0 0 0 3 3V3m-3 4h3m0 6v8m8-18v18m0-18c3 2 4 5 0 9',
    requirements:'M7 3h10v4H7V3ZM5 5H3v16h18V5h-2M7 11h10M7 15h7',
    snapshots:'M5 4h14v16H5V4Zm3-2h8v4H8V2Zm0 8h8m-8 4h8',
    purchases:'M3 5h2l2 10h10l3-7H6m3 11a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm8 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  }
  return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={paths[page]}/></svg>
}

function Application(){
  const {user,isLoading,logout}=useAuth();const [page,setPage]=useState<Page>('categories');const [navOpen,setNavOpen]=useState(false)
  const {requestNavigation}=useNavigationBlocker()
  const [sidebarCollapsed,setSidebarCollapsed]=useState(()=>{
    try{const saved=localStorage.getItem(sidebarPreferenceKey);return saved===null?window.matchMedia('(max-width: 1100px)').matches:saved==='true'}catch{return false}
  })
  const [recipeDish,setRecipeDish]=useState<Dish|null>(null);const [editingMenu,setEditingMenu]=useState<Menu|null>(null);const [purchaseId,setPurchaseId]=useState<string|null>(null)
  useEffect(()=>{try{localStorage.setItem(sidebarPreferenceKey,String(sidebarCollapsed))}catch{/* UI preference remains in memory. */}},[sidebarCollapsed])
  useEffect(()=>{
    if(!navOpen)return
    const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setNavOpen(false)}
    window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)
  },[navOpen])
  if(isLoading)return <main className="shell"><LoadingState label="系統載入中…"/></main>
  if(!user)return <LoginPage/>
  function navigate(next:Page){requestNavigation(()=>{setPage(next);setNavOpen(false)})}
  const isActive=(id:NavPage)=>page===id||(id==='dishes'&&page==='recipe')||(id==='menus'&&page==='menu-editor')
  return <div className={`app-layout ${sidebarCollapsed?'sidebar-collapsed':''}`}>
    <header className="topbar"><button className="nav-toggle secondary" aria-label={navOpen?'關閉導覽':'開啟導覽'} aria-expanded={navOpen} onClick={()=>setNavOpen(v=>!v)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button><div><span className="brand">KitchenERP</span><small>廚房營運管理</small></div><div className="account"><span>{user.display_name}</span><button className="secondary" onClick={()=>requestNavigation(()=>void logout())}>登出</button></div></header>
    <aside className={`sidebar ${navOpen?'is-open':''}`} aria-label="主要導覽">
      <div className="sidebar-controls"><button className="sidebar-toggle" aria-label={sidebarCollapsed?'展開側邊導覽':'收合側邊導覽'} aria-expanded={!sidebarCollapsed} title={sidebarCollapsed?'展開側邊導覽':'收合側邊導覽'} onClick={()=>setSidebarCollapsed(value=>!value)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={sidebarCollapsed?'m9 5 7 7-7 7':'m15 5-7 7 7 7'}/></svg><span>收合</span></button></div>
      <nav>{groups.map(group=><section className="nav-group" key={group.label}><h2>{group.label}</h2>{group.items.map(([id,label])=><button key={id} className={isActive(id)?'active':''} aria-current={isActive(id)?'page':undefined} aria-label={sidebarCollapsed?label:undefined} title={sidebarCollapsed?label:undefined} onClick={()=>navigate(id)}><NavIcon page={id}/><span>{label}</span></button>)}</section>)}</nav>
    </aside>
    {navOpen&&<button className="nav-backdrop" aria-label="關閉導覽" onClick={()=>setNavOpen(false)}/>}
    <main className="workspace" id="main-content">
      {page==='categories'&&<CategoriesPage/>}{page==='suppliers'&&<SuppliersPage/>}{page==='ingredients'&&<IngredientsPage/>}
      {page==='dishes'&&<DishesPage onEditRecipe={dish=>{setRecipeDish(dish);navigate('recipe')}}/>}{page==='recipe'&&recipeDish&&<RecipeEditor dish={recipeDish} onClose={()=>navigate('dishes')}/>}
      {page==='menus'&&<MenusPage onOpen={menu=>{setEditingMenu(menu);navigate('menu-editor')}}/>}{page==='menu-editor'&&editingMenu&&<MenuEditor menu={editingMenu} onClose={()=>navigate('menus')}/>}
      {page==='kitchen'&&<KitchenOperationsPage/>}{page==='requirements'&&<RequirementsPage/>}{page==='snapshots'&&<SnapshotsPage onPurchase={id=>{setPurchaseId(id);navigate('purchases')}}/>}{page==='purchases'&&<PurchasesPage initialId={purchaseId}/>}
    </main>
  </div>
}

export function App(){return <NavigationBlockerProvider><Application/></NavigationBlockerProvider>}
