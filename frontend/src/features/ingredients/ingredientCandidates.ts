export interface IngredientCategoryOption{id:string;name:string;is_active:boolean}
export interface IngredientSupplierOption{id:string;name:string;is_active:boolean}
interface CandidateList<T>{items:T[]}

export async function loadIngredientCandidates(
  categoryRequest:()=>Promise<CandidateList<IngredientCategoryOption>>,
  supplierRequest:()=>Promise<CandidateList<IngredientSupplierOption>>,
){
  const [categoryResult,supplierResult]=await Promise.allSettled([categoryRequest(),supplierRequest()])
  return {
    categories:categoryResult.status==='fulfilled'?categoryResult.value.items:null,
    suppliers:supplierResult.status==='fulfilled'?supplierResult.value.items:null,
    categoryFailed:categoryResult.status==='rejected',
    supplierFailed:supplierResult.status==='rejected',
  }
}

export function activeCategoryOptions(categories:IngredientCategoryOption[]){
  return categories.filter(category=>category.is_active)
}

export function editableCategoryOptions(categories:IngredientCategoryOption[],currentCategoryId:string){
  return categories.filter(category=>category.is_active||category.id===currentCategoryId)
}
