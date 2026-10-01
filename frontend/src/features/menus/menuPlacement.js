export function arrangeMenuDishes(dishes,labels){
  const columnIndexes=new Map(labels.map((column,index)=>[column.id,index]))
  const ordered=[...dishes].sort((a,b)=>a.sort_order-b.sort_order||(a.id??a.dish_id).localeCompare(b.id??b.dish_id))
  const arranged=Array.from({length:columnIndexes.size},()=>null)
  const fallback=[]
  for(const dish of ordered){
    const assignedIndex=dish.menu_meal_type_column_id===null
      ? undefined
      : columnIndexes.get(dish.menu_meal_type_column_id)
    if(assignedIndex===undefined||arranged[assignedIndex]!==null)fallback.push(dish)
    else arranged[assignedIndex]=dish
  }
  for(const dish of fallback){
    const emptyIndex=arranged.indexOf(null)
    if(emptyIndex===-1)arranged.push(dish)
    else arranged[emptyIndex]=dish
  }
  return arranged
}

export function reorderMenuDishesByColumns(dishes,columns,mealTypeId){
  const labels=[...columns]
    .filter(column=>column.menu_meal_type_id===mealTypeId)
    .sort((a,b)=>a.sort_order-b.sort_order||a.id.localeCompare(b.id))
  return arrangeMenuDishes(dishes,labels)
    .filter(dish=>dish!==null)
    .map((dish,index)=>({...dish,sort_order:index+1}))
}
