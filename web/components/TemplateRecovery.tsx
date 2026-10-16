"use client";
import { useState } from 'react';
import { supabase } from '@/lib/supabase';
import { PRODUCTION_TEMPLATES, ProductionTemplateId, configureProductionTasks } from '@/lib/productionTemplates';
import { Stage } from '@/lib/types';
export function TemplateRecovery({taskId,stages,onSaved}:{taskId:string;stages:Stage[];onSaved:()=>void}) {
  const original=stages.find(stage=>stage.kind==='render')?.params.production_template || stages.find(stage=>stage.kind==='image')?.params.production_template;
  const [id,setId]=useState<ProductionTemplateId>((PRODUCTION_TEMPLATES.find(item=>item.id===original)?.id)||'health-v1');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  return <section role="status" className="book-info-panel"><h3>模板配置尚未完成</h3><p>任务尚未开始处理。选择模板后可恢复配置。</p><select value={id} onChange={event=>setId(event.target.value as ProductionTemplateId)}>{PRODUCTION_TEMPLATES.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select><button type="button" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await configureProductionTasks(supabase,[taskId],id,{...(stages.find(stage=>stage.kind==='image')?.params||{}),image_provider:'apimart',image_model:'gpt-image-2',generation_mode:'prompt',reference_mode:'scene_continuity'});onSaved();}catch(err){setError(err instanceof Error?err.message:'配置保存失败');}finally{setBusy(false);}}}>{busy?'保存中…':'保存模板并开始'}</button>{error&&<p role="alert">{error}</p>}</section>;
}
