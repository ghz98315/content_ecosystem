import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { extractOpeningHook, markdownCell, HookScope } from '@/lib/openingHook';

export const dynamic = 'force-dynamic';

const CATEGORY_LABEL: Record<string, string> = { guoxue: '国学类', health: '健康类', social_science: '社科类', education: '教育类', scene: '场景类' };

export async function POST(request: Request) {
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    const service = process.env.SUPABASE_SERVICE_KEY;
    const bearer = request.headers.get('authorization');
    if (!url || !anon || !service) throw new Error('服务配置缺失');
    if (!bearer?.startsWith('Bearer ')) throw new Error('请重新登录');
    const body = await request.json();
    const ids = body.taskIds;
    const scope: HookScope = body.scope === 'paragraph' ? 'paragraph' : 'sentences';
    if (!Array.isArray(ids) || !ids.length || ids.length > 100 || ids.some(id => typeof id !== 'string' || !/^[0-9a-f-]{36}$/i.test(id))) {
      throw new Error('请选择 1–100 条有效任务');
    }
    const user = createClient(url, anon, { global: { headers: { Authorization: bearer } } });
    const { data: auth, error: authError } = await user.auth.getUser();
    if (authError || !auth.user) throw new Error('登录会话已失效');
    const { data: tasks, error: taskError } = await user.from('tasks').select('id,title,content_category,source_url,created_at').in('id', ids).eq('owner', auth.user.id).neq('status', 'cancelled');
    if (taskError) throw new Error(taskError.message);
    if (!tasks?.length) throw new Error('所选任务不存在或无权访问');
    const { data: artifacts, error: artifactError } = await user.from('artifacts').select('task_id,storage_path,created_at').in('task_id', tasks.map(task => task.id)).eq('stage_kind', 'transcribe').eq('type', 'transcript').order('created_at', { ascending: false });
    if (artifactError) throw new Error(artifactError.message);
    const pathByTask = new Map<string, string>();
    for (const artifact of artifacts || []) if (artifact.storage_path && !pathByTask.has(artifact.task_id)) pathByTask.set(artifact.task_id, artifact.storage_path);
    const admin = createClient(url, service);
    const lines = ['# 原始参考文案开头钩子', '', `提取范围：${scope === 'paragraph' ? '第一段' : '前四句（不足四句则全部）'}；仅使用原始逐字稿。`, '', '| 序号 | 类别 | 选题 | 原始开头钩子 | 来源链接 |', '| --- | --- | --- | --- | --- |'];
    let exported = 0;
    for (const [index, task] of ids.entries()) {
      const owned = tasks.find(item => item.id === task);
      if (!owned) continue;
      const path = pathByTask.get(task);
      if (!path) continue;
      const { data: file, error: downloadError } = await admin.storage.from('artifacts').download(path);
      if (downloadError || !file) continue;
      let transcript: { text?: string };
      try { transcript = JSON.parse(await file.text()); } catch { continue; }
      const hook = extractOpeningHook(String(transcript.text || ''), scope);
      if (!hook) continue;
      lines.push(`| ${index + 1} | ${markdownCell(CATEGORY_LABEL[owned.content_category || ''] || owned.content_category || '未分类')} | ${markdownCell(owned.title || '未命名')} | ${markdownCell(hook)} | ${markdownCell(owned.source_url || '')} |`);
      exported++;
    }
    if (!exported) throw new Error('所选任务尚无可导出的原始逐字稿');
    lines.push('', `已导出 ${exported} 条；没有原始逐字稿的任务已跳过。`, '');
    return new Response('\uFEFF' + lines.join('\n'), { headers: { 'Content-Type': 'text/markdown; charset=utf-8', 'Content-Disposition': 'attachment; filename="original-opening-hooks.md"', 'Cache-Control': 'no-store' } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '导出失败' }, { status: 400 });
  }
}
