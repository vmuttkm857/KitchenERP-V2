export interface SnapshotRevisionRequest {
  base_snapshot_id:string
  revision_intent_id:string
  criteria:unknown
  expected_result_fingerprint:string
}

/** Retain the exact body after an ambiguous network failure; never auto-retry. */
export class SnapshotRevisionIntent {
  private body:SnapshotRevisionRequest|null=null
  private binding=''
  private busy=false
  private readonly newId:()=>string
  constructor(newId:()=>string=()=>crypto.randomUUID()){this.newId=newId}
  begin(baseId:string,criteria:unknown,fingerprint:string):SnapshotRevisionRequest|null {
    if(this.busy)return null
    const binding=JSON.stringify([baseId,criteria,fingerprint])
    if(!this.body||binding!==this.binding){
      this.body={base_snapshot_id:baseId,revision_intent_id:this.newId(),
        criteria:JSON.parse(JSON.stringify(criteria)),expected_result_fingerprint:fingerprint}
      this.binding=binding
    }
    this.busy=true
    return JSON.parse(JSON.stringify(this.body))
  }
  finish(id:string,success:boolean){
    if(this.body?.revision_intent_id!==id)return
    this.busy=false
    if(success){this.body=null;this.binding=''}
  }
  invalidate(){this.body=null;this.binding='';this.busy=false}
}
