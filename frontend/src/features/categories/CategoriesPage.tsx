import { FormEvent,useCallback,useEffect,useState } from 'react'
import { apiRequest } from '../../api/client'
import { EmptyState,Feedback,LoadingState,PageHeader,StatusBadge,TableFrame } from '../../components/ui/Page'
type Kind='ingredient'|'dish'|'menu';interface Category{id:string;name:string;sort_order:number;is_active:boolean}interface List{items:Category[]}
const labels:Record<Kind,string>={ingredient:'食材分類',dish:'菜色分類',menu:'菜單分類'}
export function CategoriesPage(){
  const [kind,setKind]=useState<Kind>('ingredient'),[items,setItems]=useState<Category[]>([]),[name,setName]=useState(''),[sortOrder,setSortOrder]=useState(0),[error,setError]=useState(''),[message,setMessage]=useState(''),[loading,setLoading]=useState(true)
  const load=useCallback(async()=>{setLoading(true);try{setItems((await apiRequest<List>(`/categories/${kind}`)).items);setError('')}catch{setError('分類載入失敗，請稍後重試')}finally{setLoading(false)}},[kind]);useEffect(()=>{void load()},[load])
  async function create(e:FormEvent){e.preventDefault();try{await apiRequest(`/categories/${kind}`,{method:'POST',body:JSON.stringify({name,sort_order:sortOrder})});setName('');setMessage(`${labels[kind]}已新增`);await load()}catch{setError('分類新增失敗，名稱可能重複')}}
  async function edit(x:Category){const next=window.prompt('分類名稱',x.name);if(!next)return;await apiRequest(`/categories/${kind}/${x.id}`,{method:'PATCH',body:JSON.stringify({name:next})});setMessage('分類已修改');await load()}
  async function toggle(x:Category){await apiRequest(`/categories/${kind}/${x.id}/${x.is_active?'deactivate':'reactivate'}`,{method:'POST'});setMessage(x.is_active?'分類已停用，歷史資料仍保留':'分類已恢復');await load()}
  async function hardDelete(x:Category){if(!window.confirm(`永久刪除「${x.name}」後無法復原；被引用時系統會拒絕。`))return;const password=window.prompt('請重新輸入目前帳號密碼');if(!password)return;try{await apiRequest(`/categories/${kind}/${x.id}/hard-delete`,{method:'POST',body:JSON.stringify({password})});setMessage('未被引用的分類已永久刪除');await load()}catch{setError('資料被引用、密碼錯誤或不可永久刪除')}}
  return <section><PageHeader title="分類管理" description="管理食材、菜色與菜單分類；停用不會刪除既有歷史。"/>
    <div className="toolbar"><label>分類類型<select value={kind} onChange={e=>{setKind(e.target.value as Kind);setMessage('')}}><option value="ingredient">食材分類</option><option value="dish">菜色分類</option><option value="menu">菜單分類</option></select></label></div>
    <form className="panel-form" onSubmit={create}><label>名稱 <span aria-hidden="true">*</span><input value={name} onChange={e=>setName(e.target.value)} required/></label><label>排序<input type="number" min="0" value={sortOrder} onChange={e=>setSortOrder(Number(e.target.value))}/></label><button>新增{labels[kind]}</button></form>
    {error&&<Feedback type="error">{error}</Feedback>}{message&&<Feedback type="success">{message}</Feedback>}{loading?<LoadingState/>:!items.length?<EmptyState title={`尚無${labels[kind]}`} description="請使用上方表單新增第一筆分類。"/>:<TableFrame><table><thead><tr><th>名稱</th><th>排序</th><th>狀態</th><th>操作</th></tr></thead><tbody>{items.map(x=><tr key={x.id}><td>{x.name}</td><td>{x.sort_order}</td><td><StatusBadge active={x.is_active}/></td><td className="actions"><button className="secondary" onClick={()=>void edit(x)}>修改</button><button className="secondary" onClick={()=>void toggle(x)}>{x.is_active?'停用':'恢復'}</button><button className="secondary-danger" onClick={()=>void hardDelete(x)}>永久刪除</button></td></tr>)}</tbody></table></TableFrame>}
  </section>
}
