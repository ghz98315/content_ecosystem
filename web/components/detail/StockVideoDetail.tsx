"use client";
import {useEffect,useRef,useState} from 'react';
import {authenticatedFetch} from '@/lib/authenticatedFetch';
import {defaultStockSelection,validateStockSelection,type StockPlan,type StockSelection} from '@/lib/stockSelection';
import {Stage} from '@/lib/types';
import {DetailCommon} from './_shell';

function StockPreview({url,offset,duration}:{url:string;offset:number;duration:number}){
 const video=useRef<HTMLVideoElement>(null);
 useEffect(()=>{if(video.current&&video.current.readyState>0)video.current.currentTime=offset;},[offset]);
 return <video ref={video} controls preload="none" src={url} onLoadedMetadata={e=>{e.currentTarget.currentTime=offset;}} onTimeUpdate={e=>{if(e.currentTarget.currentTime>offset+duration)e.currentTarget.pause();}}/>;
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
 return <section className="stock-materials"><h2>视频素材清单</h2>
  <p>每段约80–100字，优先用一条视频覆盖。先确认选片，再开始拼接；沿用当前类别的标题、字幕和配乐设置。</p>
  {(!plan||current?.status==='processing'||current?.status==='pending')&&<p role="status">{current?.status==='processing'?'正在检索或准备已确认的视频素材…':'等待配音就绪后，按实际时长列出视频素材。'}</p>}
  {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
  {current?.status==='failed'&&<div role="alert"><p>{current.error}</p><button type="button" className="secondary-action" onClick={()=>onRerun(current.id)}>重试素材节点</button></div>}
  {plan&&<>
   <p>共{plan.entries.length}段 · 配音{Math.round(plan.audio_duration)}秒 · 待确认整份清单</p>
   {plan.notices?.map((notice,index)=><p className="stock-notice" key={index}>{notice}</p>)}
   <div className="stock-material-list">{plan.entries.map((entry,index)=>{
    const chosen=selection[index];const asset=entry.candidates.find(a=>a.id===chosen?.asset_id);
    return <article className="stock-material-row" key={`${revision}-${index}`}>
     <div className="stock-material-script"><h3>段落 {index+1} · {entry.word_count??entry.char_count}字 · {entry.duration.toFixed(1)}秒</h3><p>{entry.sentence}</p><small>{entry.reason}</small>
      <label>检索关键词<input value={queries[index]||''} disabled={!reviewing||busy} maxLength={100} onChange={e=>setQueries(v=>v.map((q,i)=>i===index?e.target.value:q))}/></label>
      <label>选用视频<select disabled={!reviewing||busy} value={chosen?.asset_id||''} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{asset_id:e.target.value,offset:0}:s))}><option value="">请选择足够长的视频</option>{entry.candidates.map(a=><option key={a.id} value={a.id}>{a.title} · {a.duration.toFixed(1)}秒{a.duration<entry.duration?'（时长不足）':''}</option>)}</select></label>
      {asset&&<><label>从第几秒开始截取<input type="number" min="0" max={Math.max(0,asset.duration-entry.duration)} step="0.1" disabled={!reviewing||busy} value={chosen?.offset??0} onChange={e=>setSelection(v=>v.map((s,i)=>i===index?{...s,offset:Number(e.target.value)}:s))}/></label>
      <p>截取 {Number(chosen?.offset||0).toFixed(1)}–{(Number(chosen?.offset||0)+entry.duration).toFixed(1)}秒 · {asset.width}×{asset.height}</p><p><a href={asset.page} target="_blank" rel="noreferrer">查看来源</a> · {asset.author} · <a href={asset.license_url} target="_blank" rel="noreferrer">{asset.license}</a></p></>}
     </div><div className="stock-material-preview">{asset?<StockPreview key={asset.id} url={asset.url} offset={chosen?.offset||0} duration={entry.duration}/>:<p>请选择视频，可修改关键词后重新检索。</p>}</div>
    </article>;
   })}</div>
   {reviewing&&<div className="stock-material-actions"><button type="button" className="secondary-action" disabled={busy} onClick={()=>void action('search')}>按检索词重新找视频</button><button type="button" className="primary-action" disabled={busy} onClick={()=>void action('confirm')}>确认全部选片并开始拼接</button></div>}
   {current?.status==='done'&&<p>素材已锁定，将复用于后续成片及同文案配音修改。</p>}
   <button type="button" className="secondary-action" onClick={()=>{
    const unique=new Map(plan.entries.flatMap((e,i)=>{const a=e.candidates.find(a=>a.id===selection[i]?.asset_id);return a?[[a.id,a] as const]:[];}));
    void navigator.clipboard.writeText([...unique.values()].map(a=>`${a.title} — ${a.author}；来源：${a.page}；${a.license} ${a.license_url}；已剪裁、静音并添加解说字幕。`).join('\n')).then(()=>setMessage('素材署名已复制，可放入发布简介。')).catch(()=>setError('复制失败，请从素材清单复制来源信息'));
   }}>复制素材署名</button>
  </>}
 </section>;
}
