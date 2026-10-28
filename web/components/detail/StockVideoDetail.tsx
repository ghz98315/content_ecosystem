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
 if(asset.media_type==='image')return <><div className="stock-material-actions"><button type="button" className="secondary-action" onClick={()=>setProcessed(v=>!v)}>{processed?'查看原图':'查看处理效果'}</button></div>{processed?<div className="stock-processed-preview"><img alt="模糊背景" src={asset.preview_url||asset.url} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',filter:`${filter==='none'?'':filter} blur(16px) brightness(.92)`}}/><div style={{position:'absolute',width:'100%',height:`${panelHeight}%`,top:`${(100-panelHeight)/2}%`,overflow:'hidden',maskImage:options.feather?`linear-gradient(to bottom,transparent,black ${feather}%,black ${100-feather}%,transparent)`:undefined}}><img alt={asset.title} src={asset.preview_url||asset.url} style={{position:'absolute',width:'100%',height:`${100/(1-top-bottom)}%`,top:`${-100*top/(1-top-bottom)}%`,objectFit:'cover',filter}}/></div></div>:<img alt={asset.title} src={asset.preview_url||asset.url} style={{width:'100%'}}/>}<small>公共图片按本段配音时长展示；处理预览为近似效果。</small></>;
 return <><div className="stock-material-actions"><button type="button" className="secondary-action" onClick={()=>setProcessed(v=>!v)}>{processed?'查看原片':'查看处理效果'}</button></div>
 {processed?<><div className="stock-processed-preview">
  <video ref={background} muted preload="none" src={asset.preview_url||asset.url} onLoadedMetadata={e=>{e.currentTarget.currentTime=offset;e.currentTarget.playbackRate=rate;}} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',filter:`${filter==='none'?'':filter} blur(16px) brightness(.92)`}}/>
  <div style={{position:'absolute',width:'100%',height:`${panelHeight}%`,top:`${(100-panelHeight)/2}%`,overflow:'hidden',maskImage:options.feather&&ratio!==9/16?`linear-gradient(to bottom,transparent,black ${feather}%,black ${100-feather}%,transparent)`:undefined}}>
   <video ref={video} muted preload="none" src={asset.preview_url||asset.url} {...handlers} onPlay={()=>{void background.current?.play().catch(()=>{});}} onPause={()=>background.current?.pause()} style={{position:'absolute',width:'100%',height:`${100/(1-top-bottom)}%`,top:`${-100*top/(1-top-bottom)}%`,maxHeight:'none',objectFit:'cover',filter}}/>
  </div></div><button type="button" className="secondary-action" onClick={()=>{if(video.current?.paused)void video.current.play();else video.current?.pause();}}>播放／暂停处理预览</button><small>调色为浏览器近似预览，最终以成片为准；请检查裁切是否影响人物。</small></>:<video ref={video} controls muted preload="none" src={asset.preview_url||asset.url} {...handlers}/>}</>;
}

type LocalEntry={index:number;start:number;end:number;duration:number;source_start:number;playback_rate:number;path:string;cover_source_index?:number;book_cover_pip?:{book_name:string;path:string;intervals:{start:number;end:number}[]};asset:{relative_path:string;title:string;width:number;height:number}};
function LocalStockDetail({current,onRerun}:{current:Stage;onRerun:(id:string)=>void}){
 const [entries,setEntries]=useState<LocalEntry[]>([]),[previews,setPreviews]=useState<Record<number,string>>({}),[bookPreview,setBookPreview]=useState('');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{if(!current.output_ref||!current.params.stock_source)return;let cancelled=false;
  const load=async()=>{try{
   const response=await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(current.output_ref!)}`);
   const signed=await response.json();if(!response.ok)throw new Error(signed.error||'本地素材清单读取失败');
   const index=await fetch(signed.signedUrl,{cache:'no-store'});if(!index.ok)throw new Error('本地素材清单读取失败');
   const items=await index.json() as LocalEntry[];if(cancelled)return;setEntries(items);
   const urls=await Promise.all(items.map(async item=>{try{const result=await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(item.path)}`);const data=await result.json();return [item.index,result.ok?data.signedUrl:''] as const;}catch{return [item.index,''] as const;}}));
   if(!cancelled)setPreviews(Object.fromEntries(urls));
   const coverPath=items[0]?.book_cover_pip?.path;
   if(coverPath){const result=await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(coverPath)}`);const data=await result.json();if(!cancelled)setBookPreview(result.ok?data.signedUrl:'');}
   else if(!cancelled)setBookPreview('');
  }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'本地素材清单读取失败');}};
  void load();return()=>{cancelled=true;};
 },[current.output_ref,current.params.stock_source]);
 const confirm=async()=>{setBusy(true);setError('');try{
  const result=await authenticatedFetch('/api/stock-materials',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({stageId:current.id,action:'local_confirm'})});
  const body=await result.json();if(!result.ok)throw new Error(body.error||'确认失败');setMessage('本地素材已确认，开始拼接。');
 }catch(e){setError(e instanceof Error?e.message:'确认失败');}finally{setBusy(false);}};
 return <section className="stock-materials"><h2>本地素材清单</h2><p>原视频留在本机，只上传预览图；主画面左右边缘保持清晰，仅上下羽化。系统自动选片并继续成片，清单可随时预览。</p>
  {current.status==='processing'&&<p role="status">正在按配音时长挑选本地视频…</p>}
  {current.status==='failed'&&<div role="alert"><p>{current.error}</p><button type="button" onClick={()=>onRerun(current.id)}>重试素材节点</button></div>}
  {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  {entries.length>0&&<><p>共 {entries.length} 段 · {entries.length===new Set(entries.map(item=>item.asset.relative_path)).size?'全部采用不同源片':`采用 ${new Set(entries.map(item=>item.asset.relative_path)).size} 条不同源片`}</p>
   {entries[0]?.book_cover_pip&&<p>《{entries[0].book_cover_pip.book_name}》书封将在提到书名时以画中画显示：{entries[0].book_cover_pip.intervals.map(v=>`${v.start.toFixed(1)}–${v.end.toFixed(1)} 秒`).join('、')}。</p>}
   <div className="stock-material-list">{entries.map(item=>{const pip=entries[0]?.book_cover_pip;const showPip=Boolean(pip?.intervals.some(v=>item.start<v.end&&item.end>v.start));return <article className="stock-material-row" key={item.index}><div className="stock-material-script"><h3>段落 {item.index+1} · {item.duration.toFixed(1)} 秒 {item.index===entries[0]?.cover_source_index?'· 封面画面':''}{showPip?' · 书封画中画':''}</h3><p>{item.asset.title}</p><small>{item.asset.width}×{item.asset.height} · 从 {item.source_start.toFixed(1)} 秒截取 · {item.playback_rate} 倍速</small></div><div className="stock-material-preview">{previews[item.index]?<div style={{position:'relative',width:'100%'}}><img src={previews[item.index]} alt={`第 ${item.index+1} 段素材预览`} loading="lazy" style={{maxWidth:'100%',height:'auto',display:'block'}}/>{showPip&&bookPreview&&<img src={bookPreview} alt={`《${pip?.book_name}》书封画中画示意`} style={{position:'absolute',left:'50%',top:'50%',width:'70%',height:'70%',transform:'translate(-50%,-50%)',objectFit:'contain',boxShadow:'0 3px 12px #0008'}}/>}</div>:<span>预览图加载中</span>}</div></article>;})}</div>
   {current.status==='needs_review'&&<button type="button" className="primary-action" disabled={busy} onClick={()=>void confirm()}>{busy?'确认中…':'确认本地素材并开始拼接'}</button>}
   {current.status==='done'&&<p>本地素材已选定，正在继续成片。</p>}
  </>}
 </section>;
}

export function StockVideoDetail({stage,onRerun}:DetailCommon){
 const [current,setCurrent]=useState<Stage|undefined>(stage),[selection,setSelection]=useState<StockSelection[]>([]),[queries,setQueries]=useState<string[]>([]);
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const plan=current?.params.stock_plan as StockPlan|undefined;
 const revision=plan?.revision;
 useEffect(()=>{setCurrent(stage);},[stage]);
 useEffect(()=>{if(!plan)return;setSelection((current?.params.stock_selection as StockSelection[])||defaultStockSelection(plan));setQueries(plan.entries.map(e=>e.query));},[revision]);
 if(current?.params.stock_source==='local_library')return <LocalStockDetail current={current} onRerun={onRerun}/>;
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
  <p>优先40–60秒连续画面，源片较短时允许短镜头；开阔舒展的氛围配画无需逐句对应。系统自动选片并继续拼接，清单可随时预览。</p>
  {current?.params.content_line==='health'&&<p className="stock-notice">健康类主画面4:3：优先开阔自然、阳光活力、自然人物慢镜头；避开临终、病危与血腥画面。原理解说可选非血腥结构示意。标题与标签筛选不能替代实际画面预览，请在确认前检查。</p>}
  {(!plan||current?.status==='processing'||current?.status==='pending')&&<p role="status">{current?.status==='processing'?'正在检索或准备已确认的公共素材…':'等待配音就绪后，按实际时长列出视频素材。'}</p>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  {current?.status==='failed'&&<div role="alert"><p>{current.error}</p><button type="button" className="secondary-action" onClick={()=>onRerun(current.id)}>重试素材节点</button></div>}
  {plan&&<>
   <p>共{plan.entries.length}段 · 配音{Math.round(plan.audio_duration)}秒 · {reviewing?'旧任务等待确认':'已自动选片'}</p>
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
