export interface SupplierValues{
  code:string
  name:string
  contact_person:string|null
  phone:string|null
  address:string|null
  notes:string|null
  is_active:boolean
}

function nullable(value:string|null){return value?.trim()||null}

export function normalizeSupplierValues(values:SupplierValues):SupplierValues{
  return {
    ...values,
    code:values.code.trim(),
    name:values.name.trim(),
    contact_person:nullable(values.contact_person),
    phone:nullable(values.phone),
    address:nullable(values.address),
    notes:nullable(values.notes),
  }
}
