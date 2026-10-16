export const PRODUCTION_TEMPLATES = [
  { id: 'guoxue-v1', label: '国学 · 工笔淡墨', category: 'health', style: 'guoxue_gongbi_life', preset: 'guoxue-gongbi-life', aspect: '4:3', font: 'PlayFont-ChenkunGBT', color: '#BA413B' },
  { id: 'health-v1', label: '健康 · 温暖生活', category: 'health', style: 'warm_editorial', preset: 'health-warm-editorial', aspect: '9:16', font: 'KaiTi', color: '#FFF4D9' },
  { id: 'history-v1', label: '历史社科 · 工笔淡彩', category: 'social_science', style: 'history_ink_scroll', preset: 'history-ink-scroll', aspect: '9:16', font: 'KaiTi', color: '#FFF4D9' },
  { id: 'education-v1', label: '经管 · 现代阅读', category: 'education', style: 'clean_modern', preset: 'education-clean-modern', aspect: '9:16', font: 'KaiTi', color: '#FFF4D9' },
] as const;
export type ProductionTemplateId = typeof PRODUCTION_TEMPLATES[number]['id'];
export function productionTemplate(id: string) {
  const template = PRODUCTION_TEMPLATES.find(item => item.id === id);
  if (!template) throw new Error('请选择已配置的内容模板');
  return template;
}
export async function configureProductionTasks(client: any, taskIds: string[], templateId: string, image: Record<string, unknown> = {}) {
  const template = productionTemplate(templateId);
  const imageParams = { ...image, production_template: template.id, template_version: 1, visual_style: template.style, visual_preset_id: template.preset, image_aspect_ratio: template.aspect };
  const renderParams = { production_template: template.id, template_version: 1, title_font: template.font, title_color: template.color, frame_mode: template.aspect === '4:3' ? 'landscape_blur' : 'portrait' };
  for (const [kind, params] of [['image', imageParams], ['render', renderParams]] as const) {
    const result = await client.from('stages').update({ params }).in('task_id', taskIds).eq('kind', kind).select('id');
    if (result.error || result.data?.length !== taskIds.length) throw new Error(result.error?.message || '模板保存不完整，请重试');
  }
  const result = await client.from('tasks').update({ status: 'pending' }).in('id', taskIds).eq('status', 'configuring').select('id');
  if (result.error || result.data?.length !== taskIds.length) throw new Error(result.error?.message || '任务排队失败，请重试');
}
