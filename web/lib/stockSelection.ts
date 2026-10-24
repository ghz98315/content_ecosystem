export type StockAsset = {id:string;media_type?:'video'|'image';preview_url?:string;title:string;url:string;page:string;author:string;license:string;license_url:string;duration:number;width:number;height:number;provider?:string;match_note?:string;motion_check?:{state:string}};
export type StockEntry = {index:number;sentence:string;char_count:number;word_count?:number;start:number;end:number;duration:number;query:string;reason:string;entity?:string;candidates:StockAsset[]};
export type StockProcessing = {crop_top:number;crop_bottom:number;color_style:'none'|'natural_warm_v1';feather:number};
export const LEGACY_STOCK_PROCESSING:StockProcessing={crop_top:0,crop_bottom:0,color_style:'none',feather:0};
export type StockPlan = {revision:string;audio_duration:number;entries:StockEntry[];notices:string[];processing_defaults?:StockProcessing;allowed_speeds?:number[];reuse_gap_shots?:number};
export type StockSelection = {asset_id:string;offset:number;playback_rate?:number}&Partial<StockProcessing>;
export function validateStockSelection(plan:StockPlan,selected:StockSelection[]) {
  if(!plan?.revision || !plan.entries?.length || !Array.isArray(selected) || selected.length!==plan.entries.length)throw new Error('请为每段选择一个视频');
  const result=plan.entries.map((entry,index)=>{
    const value=selected[index];const asset=entry.candidates.find(item=>item.id===value?.asset_id);
    if(!asset)throw new Error(`请选择第${index+1}段视频`);
    const offset=Number(value.offset);
    const rate=value.playback_rate??1;
    if(!(plan.allowed_speeds||[1]).includes(rate)||![1,.5,.3].includes(rate))throw new Error('不支持的素材播放速度');
    if(!Number.isFinite(offset)||offset<0||(asset.media_type==='image'?offset!==0||rate!==1:!Number.isFinite(asset.duration)||asset.duration-offset<entry.duration*rate-.05))throw new Error(`第${index+1}段素材可用时长不足，请换片、慢放或调整截取位置`);
    if(plan.reuse_gap_shots!==undefined&&selected.slice(Math.max(0,index-plan.reuse_gap_shots),index).some(s=>s.asset_id===asset.id))throw new Error('重复素材之间至少间隔一个其他镜头');
    const options={...LEGACY_STOCK_PROCESSING,...plan.processing_defaults,...value};
    for(const [key,max] of [['crop_top',.25],['crop_bottom',.25],['feather',72]] as const){
      if(!Number.isFinite(options[key])||options[key]<0||options[key]>max)throw new Error('裁切或羽化参数超出范围');
    }
    if(options.crop_top+options.crop_bottom>.4)throw new Error('上下裁切总量不能超过40%');
    if(!['none','natural_warm_v1'].includes(options.color_style))throw new Error('调色方案无效');
    return {asset_id:asset.id,offset,playback_rate:rate,crop_top:options.crop_top,crop_bottom:options.crop_bottom,color_style:options.color_style,feather:options.feather};
  });
  if(new Set(result.map(item=>item.color_style)).size>1)throw new Error('整条视频请使用同一种调色方案');
  return result;
}
export function defaultStockSelection(plan:StockPlan):StockSelection[] {
  if(plan.reuse_gap_shots!==undefined){
    const last=new Map<string,number>(),used=new Map<string,number>();
    return plan.entries.map((entry,index)=>{
      const options={...LEGACY_STOCK_PROCESSING,...plan.processing_defaults};
      const eligible=entry.candidates.filter(a=>index-(last.get(a.id)??-999)>plan.reuse_gap_shots!);
      // Prefer live library footage over the small legacy fallback directory.
      for(const pool of [eligible.filter(a=>a.provider!=='commons_catalog'),eligible])for(const reuse of [false,true])for(const rate of plan.allowed_speeds||[1]){
        const asset=pool.find(a=>a.media_type==='image'?rate===1:(a.duration-(reuse?0:used.get(a.id)||0)>=entry.duration*rate+.1));
        if(!asset)continue;
        const offset=asset.media_type==='image'||reuse?0:used.get(asset.id)||0;
        used.set(asset.id,offset+entry.duration*rate+.15);last.set(asset.id,index);
        return {...options,asset_id:asset.id,offset:Math.round(offset*100)/100,playback_rate:asset.media_type==='image'?1:rate};
      }
      return {...options,asset_id:'',offset:0,playback_rate:1};
    });
  }
  const used=new Map<string,number>();
  return plan.entries.map(entry=>{
    const asset=entry.candidates.find(a=>a.media_type==='image'||a.duration-(used.get(a.id)||0)>=entry.duration+.15);
    const options={...LEGACY_STOCK_PROCESSING,...plan.processing_defaults};
    if(!asset)return {...options,asset_id:'',offset:0};
    const offset=asset.media_type==='image'?0:used.get(asset.id)||0;if(asset.media_type!=='image')used.set(asset.id,offset+entry.duration+.2);
    return {...options,asset_id:asset.id,offset:Math.round(offset*100)/100};
  });
}
