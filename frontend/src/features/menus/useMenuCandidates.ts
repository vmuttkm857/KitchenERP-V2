import { useEffect,useRef,useState } from 'react'
import { apiRequest } from '../../api/client'
import { buildListQuery,PagedResponse,RequestSequence } from '../../utils/listQuery'
import { useDebouncedValue } from '../../utils/useDebouncedValue'
import type { Menu } from './types'

export function useMenuCandidates({active,startDate,endDate,pageSize=20,enabled=true}:{active?:string;startDate?:string;endDate?:string;pageSize?:number;enabled?:boolean}={}){
  const [search,setSearch]=useState(''),[page,setPage]=useState(1),[items,setItems]=useState<Menu[]>([]),[total,setTotal]=useState(0),[loading,setLoading]=useState(false),[error,setError]=useState('')
  const debouncedSearch=useDebouncedValue(search)
  const sequence=useRef(new RequestSequence())
  useEffect(()=>setPage(1),[active,debouncedSearch,startDate,endDate])
  useEffect(()=>{
    if(!enabled){sequence.current.next();setItems([]);setTotal(0);setLoading(false);setError('');return}
    const request=sequence.current.next();setLoading(true)
    const query=buildListQuery({page,pageSize,search:debouncedSearch,active,startDate,endDate})
    void apiRequest<PagedResponse<Menu>>(`/menus?${query}`).then(data=>{if(sequence.current.isCurrent(request)){setItems(data.items);setTotal(data.pagination.total);setError('')}}).catch(()=>{if(sequence.current.isCurrent(request))setError('菜單候選載入失敗')}).finally(()=>{if(sequence.current.isCurrent(request))setLoading(false)})
  },[active,debouncedSearch,enabled,endDate,page,pageSize,startDate])
  return {items,total,loading,error,search,setSearch,page,setPage,pageSize}
}
