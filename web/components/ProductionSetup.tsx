"use client";
import {PRODUCTION_TEMPLATES,productionTemplate,type ProductionTemplateId} from '@/lib/productionTemplates';

const names:Record<string,string>={guoxue:'国学文化',health:'健康生活',social_science:'历史社科',education:'经管阅读',scene:'城市 · 高校 · 景点'};
export type VisualMode='ai_images'|'stock_video'|'local_stock_video';
type Props={templateId:ProductionTemplateId;onTemplate:(id:ProductionTemplateId)=>void;visualMode:VisualMode;onVisualMode:(mode:VisualMode)=>void;ttsSource:'external'|'automatic';onTtsSource:(source:'external'|'automatic')=>void;inputMode?:'link'|'ready_script';disabled?:boolean};
export function ProductionSetup({templateId,onTemplate,visualMode,onVisualMode,ttsSource,onTtsSource,inputMode='link',disabled=false}:Props){
 const template=productionTemplate(templateId);
 return <div className="production-setup">
  <div className="production-settings-grid">
   <label className="production-field"><span><b>01</b> 内容类型</span><select aria-label="内容类型" disabled={disabled} value={templateId} onChange={e=>{const id=e.target.value as ProductionTemplateId;if(visualMode==='local_stock_video'&&!['guoxue','health'].includes(productionTemplate(id).category))onVisualMode('ai_images');onTemplate(id);}}>{PRODUCTION_TEMPLATES.map(t=><option key={t.id} value={t.id}>{names[t.category]}</option>)}</select><small>{inputMode==='ready_script'?'只匹配画面比例和文字样式，不重新改写':'自动匹配改写规则、画面比例和文字样式'}</small></label>
   <label className="production-field"><span><b>02</b> 画面来源</span><select aria-label="画面来源" disabled={disabled} value={visualMode} onChange={e=>onVisualMode(e.target.value as VisualMode)}><option value="ai_images">AI配图</option><option value="stock_video">网络公共素材</option>{['guoxue','health'].includes(template.category)&&<option value="local_stock_video">本地素材库</option>}</select><small>{visualMode==='local_stock_video'?'从本机 Obsidian 素材库选取视频，不上传原片':visualMode==='stock_video'?'检索网络公共素材，确认后合成':'按文案生成统一风格的分镜图片'}</small></label>
   <label className="production-field"><span><b>03</b> 配音方式</span><select aria-label="配音方式" disabled={disabled} value={ttsSource} onChange={e=>onTtsSource(e.target.value as Props['ttsSource'])}><option value="external">上传配音 · 推荐</option><option value="automatic">自动生成配音</option></select><small>{ttsSource==='external'?'先确认文案，再上传录好的音频':'确认文案后，由已配置音色生成'}</small></label>
  </div>
  <div className="production-summary"><span className="production-summary-mark" aria-hidden="true">✓</span><p><strong>{names[template.category]}</strong><span>主画面 {template.aspect} · {visualMode==='local_stock_video'?'本地素材':visualMode==='stock_video'?'网络素材':'AI配图'} · {ttsSource==='external'?'上传配音':'自动配音'}</span></p><small>设置仅用于新任务</small></div>
 </div>;
}
