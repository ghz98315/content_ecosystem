export type StockAsset = {id:string;title:string;url:string;page:string;author:string;license:string;license_url:string;duration:number;width:number;height:number;provider?:string;match_note?:string};
export type StockEntry = {index:number;sentence:string;char_count:number;word_count?:number;start:number;end:number;duration:number;query:string;reason:string;entity?:string;candidates:StockAsset[]};
export type StockPlan = {revision:string;audio_duration:number;entries:StockEntry[];notices:string[]};
export type StockSelection = {asset_id:string;offset:number};
export function validateStockSelection(plan:StockPlan,selected:StockSelection[]) {
  if(!plan?.revision || !plan.entries?.length || !Array.isArray(selected) || selected.length!==plan.entries.length)throw new Error('请为每段选择一个视频');
  return plan.entries.map((entry,index)=>{
    const value=selected[index];const asset=entry.candidates.find(item=>item.id===value?.asset_id);
    if(!asset)throw new Error(`请选择第${index+1}段视频`);
    const offset=Number(value.offset);
    if(!Number.isFinite(offset)||offset<0||!Number.isFinite(asset.duration)||asset.duration-offset<entry.duration-.05)throw new Error(`第${index+1}段视频可用时长不足，请换片或调整截取位置`);
    return {asset_id:asset.id,offset};
  });
}
export function defaultStockSelection(plan:StockPlan):StockSelection[] {
  const used=new Map<string,number>();
  return plan.entries.map(entry=>{
    const asset=entry.candidates.find(a=>a.duration-(used.get(a.id)||0)>=entry.duration+.15);
    if(!asset)return {asset_id:'',offset:0};
    const offset=used.get(asset.id)||0;used.set(asset.id,offset+entry.duration+.2);
    return {asset_id:asset.id,offset:Math.round(offset*100)/100};
  });
}
