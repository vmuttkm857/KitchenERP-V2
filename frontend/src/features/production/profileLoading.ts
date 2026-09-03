export type ProfileLoadResult<T> =
  | {kind:'found';profile:T}
  | {kind:'not-found'}
  | {kind:'error';cause:unknown}

function hasStatus(cause:unknown,status:number):boolean{
  return typeof cause==='object'&&cause!==null&&'status' in cause&&(cause as {status?:unknown}).status===status
}

export async function resolveProfileLoad<T>(request:()=>Promise<T>):Promise<ProfileLoadResult<T>>{
  try{return {kind:'found',profile:await request()}}
  catch(cause){return hasStatus(cause,404)?{kind:'not-found'}:{kind:'error',cause}}
}
