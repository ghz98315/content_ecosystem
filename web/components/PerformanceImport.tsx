"use client";
import { useMemo, useState } from 'react';
import { authenticatedFetch } from '@/lib/authenticatedFetch';
import { IMPORT_TEMPLATE, prepareImport } from '@/lib/performanceImport';

export function PerformanceImport({posts,defaultPostId,onImported}:{posts:Array<{id:string;title:string;post_url:string|null}>;defaultPostId:string;onImported:()=>Promise<void>}) {
 const [text,setText]=useState('');const [name,setName]=useState('');
 const [time,setTime]=useState(()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16));
 const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
 const preview=useMemo(()=>{if(!text)return {rows:[],errors:[]};try{return prepareImport(text,posts,time,defaultPostId);}catch(error){return {rows:[],errors:[error instanceof Error?error.message:'格式错误']};}},[text,posts,time,defaultPostId]);
 async function submit(){
  if(busy||preview.errors.length||!preview.rows.length)return;
  setBusy(true);setMessage('');
  try{
   const response=await authenticatedFetch('/api/performance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'metric_import',rows:preview.rows})});
   const data=await response.json();if(!response.ok)throw new Error(data.error||'导入失败');
   setMessage(`新增 ${data.inserted} 条，跳过 ${data.duplicates} 条重复记录。`);setText('');setName('');await onImported();
  }catch(error){setMessage(error instanceof Error?error.message:'导入失败');}finally{setBusy(false);}
 }
 function download(){const url=URL.createObjectURL(new Blob([IMPORT_TEMPLATE],{type:'text/csv;charset=utf-8'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='播放数据导入模板.csv';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 return <section style={{border:'1px solid var(--border)',borderRadius:12,padding:18,marginBottom:16}}>
  <h2 style={{fontSize:18,marginTop:0}}>批量导入播放数据</h2>
  <p style={{color:'var(--text-secondary)',fontSize:13}}>支持 UTF-8 CSV / TSV，每批最多200行。先登记作品，再填写作品ID或完全一致的作品链接；没有这两列时，使用上方选中的作品。只追加历史快照，不覆盖旧数据。此入口为文件导入，尚未连接平台自动回流。</p>
  <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
   <button onClick={download} disabled={busy} className="secondary-action">下载表头模板</button>
   <label>选择文件 <input type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];e.target.value='';setMessage('');if(!file)return;if(file.size>2_000_000){setMessage('文件超过2MB，请拆分');return;}setName(file.name);setText(await file.text());}} /></label>
   <label>缺省统计时间 <input aria-label="导入缺省统计时间" type="datetime-local" value={time} disabled={busy} onChange={e=>setTime(e.target.value)} /></label>
  </div>
  <p style={{fontSize:12,color:'var(--text-secondary)'}}>播放量必填，其他缺失指标按0占位并写入备注，请勿将占位值理解为实际统计。请使用完整整数，如12000，不能填“1.2万”。文件内的统计时间优先；无时间时使用上面的本地时间。相同作品和时刻的数据不一致时，请核对后再导入。</p>
  {name&&<p>{name} · 有效 {preview.rows.length} 行 · 错误 {preview.errors.length} 行</p>}
  {preview.errors.length>0&&<div role="alert" style={{maxHeight:160,overflow:'auto',color:'var(--danger,#e07979)'}}>{preview.errors.map((error,index)=><div key={index}>{error}</div>)}</div>}
  {preview.rows.length>0&&<div style={{maxHeight:180,overflow:'auto',fontSize:12}}>{preview.rows.slice(0,20).map((row,index)=><p key={index}>{posts.find(p=>p.id===row.postId)?.title||row.postId} · {new Date(row.recordedAt).toLocaleString()} · 播放 {row.views.toLocaleString()} {row.notes&&`· ${row.notes}`}</p>)}{preview.rows.length>20&&<p>其余 {preview.rows.length-20} 行已校验。</p>}</div>}
  <button onClick={submit} disabled={busy||!preview.rows.length||!!preview.errors.length} className="secondary-action">{busy?'正在导入…':`确认导入 ${preview.rows.length} 条快照`}</button>
  {message&&<p role="status">{message}</p>}
 </section>;
}
