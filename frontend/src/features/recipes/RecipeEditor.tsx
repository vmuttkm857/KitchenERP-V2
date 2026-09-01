import { useCallback,useEffect,useRef,useState } from 'react'
import { ApiError,apiRequest } from '../../api/client'
import type { Dish } from '../dishes/DishesPage'
import { useEditorDirty } from '../../app/NavigationBlocker'
import { completeSavedNavigation } from '../../app/navigationPolicy'
import { PaginationControls } from '../../components/ui/PaginationControls'
import { buildListQuery,PagedResponse,RequestSequence } from '../../utils/listQuery'
import { useDebouncedValue } from '../../utils/useDebouncedValue'
import { erpUnits,ErpUnit } from '../../utils/units'

interface Ingredient{id:string;code:string;name:string;category_name:string;unit:string;supplier_name:string|null}
interface Category{id:string;name:string}
interface Supplier{id:string;name:string}
interface RecipeItem{id?:string;ingredient_id:string;ingredient_code?:string;ingredient_name?:string;ingredient_unit?:string;supplier_name?:string|null;quantity:string;unit:string;loss_rate:string;sort_order:number;notes:string|null;item_cost?:string|null;cost_needs_review?:boolean}
interface Recipe{dish:Dish;items:RecipeItem[];total_cost:string|null;cost_needs_review:boolean;requirement_ready:boolean}
interface List<T>{items:T[]}
type RecipeUnit=ErpUnit
const weightUnits:RecipeUnit[]=['g','kg','斤']
const volumeUnits:RecipeUnit[]=['ml','L']

function normalizeUnit(unit:string){
  const value=unit.trim()
  if(value==='mL')return value
  if(value.toLowerCase()==='l')return 'L'
  if(['g','kg','ml'].includes(value.toLowerCase()))return value.toLowerCase()
  return value
}

function getCompatibleUnits(baseUnit:string):RecipeUnit[]{
  const normalized=normalizeUnit(baseUnit)
  if(weightUnits.includes(normalized as RecipeUnit))return weightUnits
  if(volumeUnits.includes(normalized as RecipeUnit))return volumeUnits
  return erpUnits.includes(normalized as RecipeUnit)?[normalized as RecipeUnit]:[]
}

function RecipeUnitSelect({value,baseUnit,onChange}:{value:string;baseUnit:string;onChange:(value:string)=>void}){
  const compatibleUnits=getCompatibleUnits(baseUnit),normalizedValue=normalizeUnit(value)
  const isCompatible=compatibleUnits.includes(normalizedValue as RecipeUnit)
  return <select value={isCompatible?normalizedValue:value} onChange={event=>onChange(event.target.value)}>{!isCompatible&&<option value={value} disabled>{value}（與基本單位 {baseUnit} 不相容，請改選）</option>}{compatibleUnits.map(unit=><option key={unit} value={unit}>{unit}</option>)}</select>
}

function formatCost(value:string|null|undefined,fallback='儲存後計算'){
  if(value===null||value===undefined)return fallback
  const number=Number(value);return Number.isFinite(number)?number.toFixed(4):value
}

function RecipeConfirmDialog({title,description,confirmLabel,onCancel,onConfirm}:{title:string;description:string;confirmLabel:string;onCancel:()=>void;onConfirm:()=>void}){
  useEffect(()=>{const close=(event:KeyboardEvent)=>{if(event.key==='Escape')onCancel()};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[onCancel])
  return <div className="modal-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget)onCancel()}}><section className="modal-panel recipe-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="recipe-confirm-title"><header><div><h2 id="recipe-confirm-title">{title}</h2><p>{description}</p></div></header><footer><button className="secondary" autoFocus onClick={onCancel}>留在此頁</button><button className="danger" onClick={onConfirm}>{confirmLabel}</button></footer></section></div>
}

export function RecipeEditor({dish,onClose}:{dish:Dish;onClose:()=>void}){
  const [recipe,setRecipe]=useState<Recipe|null>(null),[ingredients,setIngredients]=useState<Ingredient[]>([]),[categories,setCategories]=useState<Category[]>([]),[suppliers,setSuppliers]=useState<Supplier[]>([]),[selectedIngredient,setSelectedIngredient]=useState(''),[ingredientSearch,setIngredientSearch]=useState(''),[ingredientCategory,setIngredientCategory]=useState(''),[ingredientSupplier,setIngredientSupplier]=useState('')
  const [ingredientPage,setIngredientPage]=useState(1),[ingredientTotal,setIngredientTotal]=useState(0),[ingredientLoading,setIngredientLoading]=useState(false)
  const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[pickerError,setPickerError]=useState(''),[message,setMessage]=useState(''),[dirty,setDirty]=useState(false),[removeIndex,setRemoveIndex]=useState<number|null>(null)
  const debouncedIngredientSearch=useDebouncedValue(ingredientSearch),ingredientSequence=useRef(new RequestSequence())
  const clearEditorDirty=useEditorDirty(dirty)

  const loadRecipe=useCallback(async()=>{setLoading(true);try{setRecipe(await apiRequest<Recipe>(`/dishes/${dish.id}/recipe`));setDirty(false);setError('')}catch{setError('配方資料載入失敗')}finally{setLoading(false)}},[dish.id])
  useEffect(()=>{void loadRecipe()},[loadRecipe])
  useEffect(()=>{void Promise.all([apiRequest<List<Category>>('/categories/ingredient?active=true&page_size=100'),apiRequest<List<Supplier>>('/suppliers?active=true&page_size=100')]).then(([categoryList,supplierList])=>{setCategories(categoryList.items);setSuppliers(supplierList.items)}).catch(()=>setError('食材篩選選項載入失敗'))},[])
  useEffect(()=>{const request=ingredientSequence.current.next();setIngredientLoading(true);const query=buildListQuery({page:ingredientPage,pageSize:25,active:'true',search:debouncedIngredientSearch,categoryId:ingredientCategory,supplierId:ingredientSupplier});void apiRequest<PagedResponse<Ingredient>>(`/ingredients?${query}`).then(result=>{if(ingredientSequence.current.isCurrent(request)){setIngredients(result.items);setIngredientTotal(result.pagination.total);setPickerError('')}}).catch(()=>{if(ingredientSequence.current.isCurrent(request))setPickerError('候選食材載入失敗')}).finally(()=>{if(ingredientSequence.current.isCurrent(request))setIngredientLoading(false)})},[debouncedIngredientSearch,ingredientCategory,ingredientPage,ingredientSupplier])

  function addIngredient(){const ingredient=ingredients.find(item=>item.id===selectedIngredient);if(!ingredient||!recipe||recipe.items.some(item=>item.ingredient_id===ingredient.id))return;setRecipe({...recipe,items:[...recipe.items,{ingredient_id:ingredient.id,ingredient_code:ingredient.code,ingredient_name:ingredient.name,ingredient_unit:ingredient.unit,supplier_name:ingredient.supplier_name,quantity:'0',unit:normalizeUnit(ingredient.unit),loss_rate:'0',sort_order:recipe.items.length+1,notes:null}]});setSelectedIngredient('');setDirty(true);setMessage('')}
  function update(index:number,changes:Partial<RecipeItem>){if(!recipe)return;setRecipe({...recipe,items:recipe.items.map((item,position)=>position===index?{...item,...changes}:item)});setDirty(true);setMessage('')}
  function remove(index:number){if(!recipe)return;setRecipe({...recipe,items:recipe.items.filter((_,position)=>position!==index)});setRemoveIndex(null);setDirty(true);setMessage('')}
  function requestClose(){onClose()}
  async function save(returnAfter:boolean){if(!recipe)return;setSaving(true);setMessage('');try{const saved=await apiRequest<Recipe>(`/dishes/${dish.id}/recipe`,{method:'PUT',body:JSON.stringify({items:recipe.items.map(item=>({id:item.id,ingredient_id:item.ingredient_id,quantity:item.quantity,unit:item.unit,loss_rate:item.loss_rate,sort_order:item.sort_order,notes:item.notes}))})});setRecipe(saved);setDirty(false);setError('');if(returnAfter)completeSavedNavigation(clearEditorDirty,onClose);else setMessage('配方已儲存')}catch(cause){setError(cause instanceof ApiError&&cause.status===422?cause.message:'配方儲存失敗；所有變更均未寫入，請檢查食材、數量、單位與耗損率')}finally{setSaving(false)}}

  if(loading||!recipe)return <section><button className="back-link" onClick={requestClose}>← 返回菜色管理</button><p>{loading?'配方載入中…':error}</p></section>
  return <section className="recipe-editor-page"><nav className="recipe-breadcrumb" aria-label="麵包屑"><button className="back-link" onClick={requestClose}>← 返回菜色管理</button><span>菜色管理</span><span aria-hidden="true">›</span><span>{dish.name}</span><span aria-hidden="true">›</span><strong>標準配方</strong></nav><div className="section-heading"><div><p className="eyebrow">標準配方</p><h2>{dish.code}｜{dish.name}</h2>{dirty&&<span className="unsaved-indicator">有尚未儲存的變更</span>}</div></div>
    <div className="recipe-picker recipe-picker-filtered"><label className="recipe-search">搜尋食材<input value={ingredientSearch} onChange={event=>{setIngredientSearch(event.target.value);setIngredientPage(1);setSelectedIngredient('')}}/></label><label className="recipe-candidate">選擇食材<select disabled={ingredientLoading||!ingredients.length} value={selectedIngredient} onChange={event=>setSelectedIngredient(event.target.value)}><option value="">{ingredientLoading?'載入中…':ingredients.length?'請選擇':'沒有符合條件的食材'}</option>{ingredients.filter(candidate=>!recipe.items.some(item=>item.ingredient_id===candidate.id)).map(item=><option key={item.id} value={item.id}>{item.code}｜{item.name}｜{item.category_name}｜{item.supplier_name??'無供應商'}</option>)}</select></label><label className="recipe-category">食材分類<select value={ingredientCategory} onChange={event=>{setIngredientCategory(event.target.value);setIngredientPage(1);setSelectedIngredient('')}}><option value="">全部分類</option>{categories.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="recipe-supplier">供應商<select value={ingredientSupplier} onChange={event=>{setIngredientSupplier(event.target.value);setIngredientPage(1);setSelectedIngredient('')}}><option value="">全部供應商</option>{suppliers.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button type="button" onClick={addIngredient} disabled={!selectedIngredient}>加入配方</button><PaginationControls page={ingredientPage} pageSize={25} total={ingredientTotal} onPage={page=>{setIngredientPage(page);setSelectedIngredient('')}}/></div>
    {pickerError&&<p className="error">{pickerError}</p>}{error&&<p className="error">{error}</p>}{message&&<p className="success">{message}</p>}
    <table><thead><tr><th>順序</th><th>食材</th><th>每人用量</th><th>配方單位</th><th>耗損率 %</th><th>備註</th><th>成本</th><th>操作</th></tr></thead><tbody>{recipe.items.map((item,index)=><tr key={item.id??item.ingredient_id}><td><input type="number" min="0" value={item.sort_order} onChange={event=>update(index,{sort_order:Number(event.target.value)})}/></td><td>{item.ingredient_code}｜{item.ingredient_name}<small>{item.supplier_name?`｜${item.supplier_name}`:''}</small></td><td><input type="number" min="0" step="0.000001" value={item.quantity} onChange={event=>update(index,{quantity:event.target.value})}/></td><td><RecipeUnitSelect value={item.unit} baseUnit={item.ingredient_unit??item.unit} onChange={unit=>update(index,{unit})}/></td><td><input type="number" min="0" step="0.000001" value={item.loss_rate} onChange={event=>update(index,{loss_rate:event.target.value})}/></td><td><input value={item.notes??''} onChange={event=>update(index,{notes:event.target.value||null})}/></td><td>{item.cost_needs_review?'待確認':formatCost(item.item_cost)}</td><td><button className="danger" onClick={()=>setRemoveIndex(index)}>移除關聯</button></td></tr>)}</tbody></table>
    <div className="recipe-summary"><strong>單份成本：{recipe.cost_needs_review?'待確認':formatCost(recipe.total_cost,'0.0000')}</strong><span>{recipe.requirement_ready?'配方完整，可進行需求量計算。':'配方尚未完成：有食材的每人用量為 0，暫時無法計算需求量。'}</span><div className="recipe-save-actions"><button className="secondary" onClick={()=>void save(false)} disabled={saving||!dirty}>{saving?'儲存中…':'僅儲存'}</button><button onClick={()=>void save(true)} disabled={saving}>{saving?'儲存中…':'儲存並返回'}</button></div></div>
    {removeIndex!==null&&<RecipeConfirmDialog title="移除配方食材" description="只會移除此配方關聯，不會刪除食材主檔。" confirmLabel="確認移除" onCancel={()=>setRemoveIndex(null)} onConfirm={()=>remove(removeIndex)}/>}
  </section>
}
