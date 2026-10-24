export type StockAsset = {id:string;title:string;url:string;page:string;author:string;license:string;license_url:string;duration:number;width:number;height:number;provider?:string;match_note?:string;motion_check?:{state:string}};
export type StockEntry = {index:number;sentence:string;char_count:number;word_count?:number;start:number;end:number;duration:number;query:string;reason:string;entity?:string;candidates:StockAsset[]};
export type StockProcessing = {crop_top:number;crop_bottom:number;color_style:'none'|'natural_warm_v1';feather:number};
export const LEGACY_STOCK_PROCESSING:StockProcessing={crop_top:0,crop_bottom:0,color_style:'none',feather:0};
export type StockPlan = {revision:string;audio_duration:number;entries:StockEntry[];notices:string[];processing_defaults?:StockProcessing};
export type StockSelection = {asset_id:string;offset:number}&Partial<StockProcessing>;
export function validateStockSelection(plan:StockPlan,selected:StockSelection[]) {
  if(!plan?.revision || !plan.entries?.length || !Array.isArray(selected) || selected.length!==plan.entries.length)throw new Error('请为每段选择一个视频');
  const result=plan.entries.map((entry,index)=>{
    const value=selected[index];const asset=entry.candidates.find(item=>item.id===value?.asset_id);
    if(!asset)throw new Error(`请选择第${index+1}段视频`);
    const offset=Number(value.offset);
    if(!Number.isFinite(offset)||offset<0||!Number.isFinite(asset.duration)||asset.duration-offset<entry.duration-.05)throw new Error(`第${index+1}段视频可用时长不足，请换片或调整截取位置`);
    const options={...LEGACY_STOCK_PROCESSING,...plan.processing_defaults,...value};
    for(const [key,max] of [['crop_top',.25],['crop_bottom',.25],['feather',72]] as const){
      if(!Number.isFinite(options[key])||options[key]<0||options[key]>max)throw new Error('裁切或羽化参数超出范围');
    }
    if(options.crop_top+options.crop_bottom>.4)throw new Error('上下裁切总量不能超过40%');
    if(!['none','natural_warm_v1'].includes(options.color_style))throw new Error('调色方案无效');
    return {asset_id:asset.id,offset,crop_top:options.crop_top,crop_bottom:options.crop_bottom,color_style:options.color_style,feather:options.feather};
  });
  if(new Set(result.map(item=>item.color_style)).size>1)throw new Error('整条视频请使用同一种调色方案');
  return result;
}
export function defaultStockSelection(plan:StockPlan):StockSelection[] {
  const used=new Map<string,number>();
  return plan.entries.map(entry=>{
    const asset=entry.candidates.find(a=>a.duration-(used.get(a.id)||0)>=entry.duration+.15);
    const options={...LEGACY_STOCK_PROCESSING,...plan.processing_defaults};
    if(!asset)return {...options,asset_id:'',offset:0};
    const offset=used.get(asset.id)||0;used.set(asset.id,offset+entry.duration+.2);
    return {...options,asset_id:asset.id,offset:Math.round(offset*100)/100};
  });
}
