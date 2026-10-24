"use client";
import {useEffect,useRef,useState} from 'react';
import {authenticatedFetch} from '@/lib/authenticatedFetch';
import {defaultStockSelection,validateStockSelection,LEGACY_STOCK_PROCESSING,type StockPlan,type StockSelection,type StockAsset} from '@/lib/stockSelection';
import {Stage} from '@/lib/types';
import {DetailCommon} from './_shell';

function StockPreview({asset,offset,duration,selection,aspect}:{asset:StockAsset;offset:number;duration:number;selection:StockSelection;aspect:string}){
 const video=useRef<HTMLVideoElement>(null),background=useRef<HTMLVideoElement>(null);
 const [processed,setProcessed]=useState(false);
 const options={...LEGACY_STOCK_PROCESSING,...selection};
 const top=options.crop_top,bottom=options.crop_bottom;
 const rate=selection.playback_rate??1;
 const ratio=aspect==='1:1'?1:aspect==='4:3'?4/3:9/16;
 const panelHeight=100*9/16/ratio;
 const filter=options.color_style==='natural_warm_v1'?'sepia(.04) saturate(.94) contrast(1.015) brightness(1.006)':'none';
 const feather=options.feather/1080*100;
 useEffect(()=>{if(video.current){video.current.playbackRate=rate;if(video.current.readyState>0)video.current.currentTime=offset;}if(background.current)background.current.playbackRate=rate;},[offset,rate]);
 const handlers={onLoadedMetadata:(e:React.SyntheticEvent<HTMLVideoElement>)=>{e.currentTarget.currentTime=offset;e.currentTarget.playbackRate=rate;},onTimeUpdate:(e:React.SyntheticEvent<HTMLVideoElement>)=>{
  if(e.currentTarget.currentTime>offset+duration*rate)e.currentTarget.pause();
  if(background.current&&Math.abs(background.current.currentTime-e.currentTarget.currentTime)>.2)background.current.currentTime=e.currentTarget.currentTime;
 }};
 if(asset.media_type==='image')return <><div className="stock-material-actions"><button type="button" className="secondary-action" onClick={()=>setProcessed(v=>!v)}>{processed?'查看原图':'查看处理效果'}</button></div>{processed?<div className="stock-processed-preview"><img alt="模糊背景" src={asset.preview_url||asset.url} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',filter:`${filter==='none'?'':filter} blur(16px) brightness(.92)`}}/><div style={{position:'absolute',width:'100%',height:`${panelHeight}%`,top:`${(100-panelHeight)/2}%`,overflow:'hidden',maskImage:options.feather?`linear-gradient(to bottom,transparent,black ${feather}%,black ${100-feather}%,transparent),linear-gradient(to right,transparent,black ${feather}%,black ${100-feather}%,transparent)`:undefined,maskComposite:'intersect'}}><img alt={asset.title} src={asset.preview_url||asset.url} style={{position:'absolute',width:'100%',height:`${100/(1-top-bottom)}%`,top:`${-100*top/(1-top-bottom)}%`,objectFit:'cover',filter}}/></div></div>:<img alt={asset.title} src={asset.preview_url||asset.url} style={{width:'100%'}}/>}<small>公共图片按本段配音时长展示；处理预览为近似效果。</small></>;
 return <><div className="stock-material-actions"><button type="button" className="secondary-action" onClick={()=>setProcessed(v=>!v)}>{processed?'查看原片':'查看处理效果'}</button></div>
 {processed?<><div className="stock-processed-preview">
  <video ref={background} muted preload="none" src={asset.preview_url||asset.url} onLoadedMetadata={e=>{e.currentTarget.currentTime=offset;e.currentTarget.playbackRate=rate;}} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',filter:`${filter==='none'?'':filter} blur(16px) brightness(.92)`}}/>
  <div style={{position:'absolute',width:'100%',height:`${panelHeight}%`,top:`${(100-panelHeight)/2}%`,overflow:'hidden',maskImage:options.feather&&ratio!==9/16?`linear-gradient(to bottom,transparent,black ${feather}%,black ${100-feather}%,transparent),linear-gradient(to right,transparent,black ${feather}%,black ${100-feather}%,transparent)`:undefined,maskComposite:'intersect'}}>
   <video ref={video} muted preload="none" src={asset.preview_url||asset.url} {...handlers} onPlay={()=>{void background.current?.play().catch(()=>{});}} onPause={()=>background.current?.pause()} style={{position:'absolute',width:'100%',height:`${100/(1-top-bottom)}%`,top:`${-100*top/(1-top-bottom)}%`,maxHeight:'none',objectFit:'cover',filter}}/>
  </div></div><button type="button" className="secondary-action" onClick={()=>{if(video.current?.paused)void video.current.play();else video.current?.pause();}}>播放／暂停处理预览</button><small>调色为浏览器近似预览，最终以成片为准；请检查裁切是否影响人物。</small></>:<video ref={video} controls muted preload="none" src={asset.preview_url||asset.url} {...handlers}/>}</>;
}

export function StockVideoDetail({stage,onRerun}:DetailCommon){
 const [current,setCurrent]=useState<Stage|undefined>(stage),[selection,setSelection]=useState<StockSelection[]>([]),[queries,setQueries]=useState<string[]>([]);
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const plan=current?.params.stock_plan as StockPlan|undefined;
 const revision=plan?.revision;
 useEffect(()=>{setCurrent(stage);},[stage]);
 useEffect(()=>{if(!plan)return;setSelection((current?.params.stock_selection as StockSelection[])||defaultStockSelection(plan));setQueries(plan.entries.map(e=>e.query));},[revision]);
 async function action(name:'confirm'|'search'){
   if(!current||!plan)return;setBusy(true);setError('');
   try{
     if(name==='confirm')validateStockSelection(plan,selection);
     const result=await authenticatedFetch('/api/stock-materials',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({stageId:current.id,revision:plan.revision,action:name,selections:selection,queries})});
     const body=await result.json();if(!result.ok)throw new Error(body.error||'保存失败');
     setCurrent({...current,status:'pending'});setMessage(name==='confirm'?'素材已确认，开始准备视频并拼接。':'正在按新的检索词重新寻找视频，完成后请确认清单。');
   }catch(e){setError(e instanceof Error?e.message:'提交失败');}finally{setBusy(false);}
 }
 const reviewing=current?.status==='needs_review';
 return <section className="stock-materials"><h2>公共素材清单</h2>
  <p>优先40–60秒连续画面，源片较短时允许短镜头；开阔舒展的氛围配画无需逐句对应。先确认选片，再开始拼接；沿用当前类别的标题、字幕和配乐设置。</p>
  {current?.params.content_line==='health'&&<p className="stock-notice">健康类主画面4:3：优先开阔自然、阳光活力、自然人物慢镜头；避开临终、病危与血腥画面。原理解说可选非血腥结构示意。标题与标签筛选不能替代实际画面预览，请在确认前检查。</p>}
  {(!plan||current?.status==='processing'||current?.status==='pending')&&<p role="status">{current?.status==='processing'?'正在检索或准备已确认的公共素材…':'等待配音就绪后，按实际时长列出视频素材。'}</p>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  {current?.status==='failed'&&<div role="alert"><p>{current.error}</p><button type="button" className="secondary-action" onClick={()=>onRerun(current.id)}>重试素材节点</button></div>}
  {plan&&<>
   <p>共{plan.entries.length}段 · 配音{Math.round(plan.audio_duration)}秒 · 待确认整份清单</p>
   {plan.notices?.map((notice,index)=><p className="stock-notice" key={index}>{notice}</p>)}
   <div className="stock-processing-controls"><label>统一画面色彩<select disabled={!reviewing||busy} value={selection[0]?.color_style??plan.processing_defaults?.color_style??'none'} onChange={e=>setSelection(items=>items.map(item=>({...item,color_style:e.target.value as 'none'|'natural_warm_v1'})))}><option value="natural_warm_v1">自然通透 · 微暖柔和</option><option value="none">保留原色</option></select></label>
   <label>边缘羽化 {selection[0]?.feather??plan.processing_defaults?.feather??0}px<input type="range" min="0" max="72" step="6" disabled={!reviewing||busy} value={selection[0]?.feather??plan.processing_defaults?.feather??0} onChange={e=>setSelection(items=>items.map(item=>({...item,feather:Number(e.target.value)})))}/></label><small>羽化用于带模糊背景的主画面；字幕、标题和脚注保持清晰。</small></div>
   <div className="stock-material-list">{plan.entries.map((entry,index)=>{
    const chosen=selection[index];const asset=entry.candidates.find(a=>a.id===chosen?.asset_id);
    return <article className="stock-material-row" key={`${revision}-${index}`}>
     <div className="stock-material-script"><h3>段落 {index+1} · {entry.word_count??entry.char_count}字 · {entry.duration.toFixed(1)}秒</h3><p>{entry.sentence}</p><small>{entry.reason}</small>
      <label>检索关键词<input value={queries[index]||''} disabled={!reviewing||busy} maxLength={100} onChange={e=>setQueries(v=>v.map((q,i)=>i===index?e.target.value:q))}/></label>
      <label>选用素材<select disabled={!reviewing||busy} value={chosen?.asset_id||''} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{...s,asset_id:e.target.value,offset:0}:s))}><option value="">请选择公共视频或图片</option>{entry.candidates.map(a=><option key={a.id} value={a.id}>{a.title} · {a.media_type==='image'?'图片':`${a.duration.toFixed(1)}秒`}{a.media_type!=='image'&&a.duration/Math.min(...(plan.allowed_speeds||[1]))<entry.duration?'（时长不足）':''}</option>)}</select></label>
      {asset&&<>{asset.media_type!=='image'&&<label>播放速度<select disabled={!reviewing||busy} value={chosen?.playback_rate??1} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{...s,playback_rate:Number(e.target.value)}:s))}>{(plan.allowed_speeds||[1]).map(rate=><option key={rate} value={rate}>{rate}倍{rate===1?'（正常）':'（慢放）'}</option>)}</select><small>仅调整素材视频，配音速度不变。</small></label>}{asset.media_type!=='image'&&<label>从第几秒开始截取<input type="number" min="0" max={Math.max(0,asset.duration-entry.duration*(chosen?.playback_rate??1))} step="0.1" disabled={!reviewing||busy} value={chosen?.offset??0} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{...s,offset:Number(e.target.value)}:s))}/></label>}
      {(['crop_top','crop_bottom'] as const).map(key=><label key={key}>{key==='crop_top'?'裁掉顶部原字幕区域':'裁掉底部原字幕区域'} {Math.round((chosen?.[key]||0)*100)}%<input type="range" min="0" max="25" step="1" value={Math.round((chosen?.[key]||0)*100)} disabled={!reviewing||busy} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{...s,[key]:Number(e.target.value)/100}:s))}/></label>)}
      <p>{asset.media_type==='image'?'图片展示':'截取'} {Number(chosen?.offset||0).toFixed(1)}–{(Number(chosen?.offset||0)+entry.duration*(chosen?.playback_rate??1)).toFixed(1)}秒 · {asset.width}×{asset.height}</p><p><a href={asset.page} target="_blank" rel="noreferrer">查看来源</a> · {asset.author} · <a href={asset.license_url} target="_blank" rel="noreferrer">{asset.license}</a></p></>}
      {asset?.motion_check?.state==='nearly_static'&&<p>该候选的已检查片段几乎静止，建议优先换用有运镜或人物活动的视频。</p>}
     </div><div className="stock-material-preview">{asset&&chosen?<StockPreview key={asset.id} asset={asset} offset={chosen.offset||0} duration={entry.duration} selection={chosen} aspect={String(current?.params.image_aspect_ratio||'1:1')}/>:<p>请选择视频，可修改关键词后重新检索。</p>}</div>
    </article>;
   })}</div>
   {reviewing&&<div className="stock-material-actions"><button type="button" className="secondary-action" disabled={busy} onClick={()=>{setSelection(defaultStockSelection(plan));setMessage('已按间隔复用与可用速度补齐，请预览后确认。');}}>自动补齐可用素材</button><button type="button" className="secondary-action" disabled={busy} onClick={()=>void action('search')}>按检索词重新找素材</button><button type="button" className="primary-action" disabled={busy} onClick={()=>void action('confirm')}>确认全部选片并开始拼接</button></div>}
   {current?.status==='done'&&<p>素材已锁定，将复用于后续成片及同文案配音修改。</p>}
   <button type="button" className="secondary-action" onClick={()=>{
    const unique=new Map(plan.entries.flatMap((e,i)=>{const a=e.candidates.find(a=>a.id===selection[i]?.asset_id);return a?[[a.id,a] as const]:[];}));
    void navigator.clipboard.writeText([...unique.values()].map(a=>`${a.title} — ${a.author}；来源：${a.page}；${a.license} ${a.license_url}；已剪裁、静音并添加解说字幕。`).join('\n')).then(()=>setMessage('素材署名已复制，可放入发布简介。')).catch(()=>setError('复制失败，请从素材清单复制来源信息'));
   }}>复制素材署名</button>
  </>}
 </section>;
}
