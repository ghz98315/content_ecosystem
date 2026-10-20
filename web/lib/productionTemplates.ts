import manifest from './productionTemplateManifest.json';
export type ProductionTemplateId = 'guoxue-v1' | 'health-v1' | 'history-v1' | 'education-v1';
type TemplateDefinition = { id:ProductionTemplateId; label:string; category:'guoxue'|'health'|'social_science'|'education'; style:string; preset:string; aspect:'4:3'|'9:16'; frameMode:'landscape_blur'|'portrait'; gridCells:number; gridResolution?:'2k'; font:string; color:string };
/** Shared by the website and Worker: one source for the visual contract. */
export const PRODUCTION_TEMPLATES = manifest as readonly TemplateDefinition[];
export function productionTemplate(id: string) {
  const template = PRODUCTION_TEMPLATES.find(item => item.id === id);
  if (!template) throw new Error('请选择已配置的内容模板');
  return template;
}
export async function configureProductionTasks(client: any, taskIds: string[], templateId: string, image: Record<string, unknown> = {}) {
  const template = productionTemplate(templateId);
  const imageParams = { ...image, production_template: template.id, template_version: 1, content_line: template.category, visual_style: template.style, visual_preset_id: template.preset, image_aspect_ratio: template.aspect, ...(template.gridResolution ? { grid_resolution: template.gridResolution } : {}) };
  const renderParams = { production_template: template.id, template_version: 1, content_line: template.category, title_font: template.font, title_color: template.color, frame_mode: template.frameMode };
  const { data: rewriteStages, error: rewriteError } = await client.from('stages').select('id,task_id,params').in('task_id', taskIds).eq('kind', 'rewrite');
  if (rewriteError || rewriteStages?.length !== taskIds.length) throw new Error(rewriteError?.message || '文案规则快照不完整，请重试');
  for (const stage of rewriteStages) {
    const rewriteDomain = template.category === 'guoxue' || template.category === 'health' ? template.category : 'auto';
    const result = await client.from('stages').update({ params: { ...(stage.params || {}), content_line: template.category, rewrite_domain: rewriteDomain } }).eq('id', stage.id).eq('task_id', stage.task_id).select('id');
    if (result.error || result.data?.length !== 1) throw new Error(result.error?.message || '文案规则保存失败，请重试');
  }
  for (const [kind, params] of [['image', imageParams], ['render', renderParams]] as const) {
    const result = await client.from('stages').update({ params }).in('task_id', taskIds).eq('kind', kind).select('id');
    if (result.error || result.data?.length !== taskIds.length) throw new Error(result.error?.message || '模板保存不完整，请重试');
  }
  const result = await client.from('tasks').update({ status: 'pending', content_category: template.category }).in('id', taskIds).eq('status', 'configuring').select('id');
  if (result.error || result.data?.length !== taskIds.length) throw new Error(result.error?.message || '任务排队失败，请重试');
}
