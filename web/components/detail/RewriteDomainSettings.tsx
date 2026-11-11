"use client";
import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Stage } from '@/lib/types';

export interface RewriteSkillInfo {
 domain: string; label: string; version: string; reason: string;
 information_card?: Array<{id:string;source_quote:string;summary:string}>;
 rewrite_outline?: Array<{purpose:string;fact_ids:string[];target_quote:string}>;
 fact_semantics_status?:string;
}
const choices = [['auto','自动判断，冲突时确认'],['guoxue','国学'],['health','女性成长与健康生活'],['mixed','国学与健康混合'],['general','通用'],['scene','山河人文'],['history','历史社科']] as const;
export function RewriteDomainSettings({taskId,stage,applied}:{taskId:string;stage?:Stage;applied?:RewriteSkillInfo}) {
 const [domain,setDomain]=useState('auto');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
 const historyLine = stage?.params?.content_line === 'social_science' || applied?.domain === 'history';
 const saved=historyLine ? 'history' : String(stage?.params?.rewrite_domain || 'auto');
 const needsDomainChange = stage?.status === 'needs_review' && !stage.output_ref &&
  /正文包含|正文健康主题冲突|正文经典主题冲突|二创领域无效|山河人文.*二创规则/.test(stage.error || '');
 useEffect(()=>{setDomain(saved);setMessage('');},[stage?.id,saved]);
 async function save(){
  if(!stage)return;setBusy(true);setMessage('');
  try {
   const {data:current,error}=await supabase.from('stages').select('params,status,updated_at').eq('id',stage.id).eq('task_id',taskId).single();
   if(error||!current)throw new Error('读取改写设置失败');
   if(current.status==='processing')throw new Error('正在改写，请本次完成后再修改领域');
   const params = {...current.params, rewrite_domain: domain};
   const {data,error:writeError}=await supabase.from('stages').update({params}).eq('id',stage.id).eq('updated_at',current.updated_at).neq('status','processing').select('id');
   if(writeError)throw writeError;if(!data?.length)throw new Error('状态已变化，请重试');
   setMessage('改写设置已保存，重新运行改写节点时生效。');
  }catch(e){setMessage(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
 }
 if (!applied && !needsDomainChange) return null;
 return <section className="book-info-panel" aria-label="二创内容领域" style={{padding:16,marginBottom:16}}>
  {needsDomainChange && <><h3>确认二创内容领域</h3>
  <div className="external-actions"><select aria-label="选择二创领域" value={domain} disabled={busy||stage?.status==='processing'} onChange={e=>setDomain(e.target.value)}>{choices.filter(([value])=>historyLine ? value==='history' : stage?.params?.content_line==='scene'?value==='scene':!['scene','history'].includes(value)).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>
   <button type="button" className="secondary-action" onClick={()=>void save()} disabled={busy||!stage||stage.status==='processing'}>{busy?'保存中…':'保存改写设置'}</button></div>
  {message&&<p role="status">{message}</p>}</>}
  {applied&&<><p>本稿实际采用：<strong>{applied.label}</strong> · skill {applied.version} · {applied.reason}</p>
   {!!applied.information_card?.length&&<details><summary>查看信息卡与实际提纲</summary><p>{applied.fact_semantics_status}</p><ol>{applied.information_card.map(f=><li key={f.id}><strong>{f.id} · {f.summary}</strong><blockquote>原稿依据：{f.source_quote}</blockquote></li>)}</ol><h4>提纲落点</h4><ol>{applied.rewrite_outline?.map((part,index)=><li key={index}>{part.purpose}（{part.fact_ids.join('、')}）<blockquote>成稿锚点：{part.target_quote}</blockquote></li>)}</ol></details>}</>}
 </section>;
}
