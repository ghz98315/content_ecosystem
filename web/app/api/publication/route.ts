import { createHash, randomUUID } from 'node:crypto';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { PUBLICATION_PROMPT, validatePublication } from '@/lib/publication';
import { splitSourceDescription } from '@/lib/sourceMetadata';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
class RequestError extends Error { constructor(message: string, public status = 400) { super(message); } }
const response = (body: unknown, status = 200) => NextResponse.json(body, { status, headers: { 'Cache-Control': 'no-store' } });

async function context(request: NextRequest, taskId: string) {
  if (!UUID.test(taskId)) throw new RequestError('任务编号无效');
  const token = request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/i)?.[1];
  if (!token) throw new RequestError('请先连接工作区', 401);
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new RequestError('服务配置缺失', 503);
  const db = createClient(url, key, { auth: { persistSession: false } });
  const { data: auth, error: authError } = await db.auth.getUser(token);
  if (authError || !auth.user) throw new RequestError('登录会话已失效', 401);
  const { data: task, error } = await db.from('tasks').select('id,title,source_tags,content_category').eq('id', taskId).eq('owner', auth.user.id).maybeSingle();
  if (error) throw new RequestError('读取任务失败', 503);
  if (!task) throw new RequestError('无权访问该任务', 403);
  return { db, task };
}

async function scriptContext(db: SupabaseClient, taskId: string) {
  const { data: stage, error } = await db.from('stages').select('status,params,output_ref').eq('task_id', taskId).eq('kind', 'rewrite').single();
  if (error) throw new RequestError('读取文案状态失败', 503);
  if (stage.status !== 'done') return null;
  let text = typeof stage.params?.final_text === 'string' ? stage.params.final_text.trim() : '';
  if (!text && stage.output_ref) {
    const path = String(stage.output_ref);
    if (!path.startsWith(`${taskId}/`) || path.includes('\\') || path.split('/').includes('..')) throw new RequestError('文案路径无效');
    const { data, error: downloadError } = await db.storage.from('artifacts').download(path);
    if (downloadError || !data) throw new RequestError('确认稿读取失败，请稍后重试', 503);
    const payload = JSON.parse(await data.text());
    text = typeof payload.final_text === 'string' ? payload.final_text.trim() : '';
  }
  if (!text) return null;
  return { text, hash: createHash('sha256').update(text).digest('hex') };
}

async function latest(db: SupabaseClient, taskId: string) {
  const { data, error } = await db.from('artifacts').select('id,meta,created_at').eq('task_id', taskId).eq('type', 'publication_copy').order('created_at', { ascending: false }).order('id', { ascending: false }).limit(1);
  if (error) throw new RequestError('发布文案读取失败', 503);
  return data?.[0] || null;
}

export async function GET(request: NextRequest) {
  try {
    const { db, task } = await context(request, request.nextUrl.searchParams.get('taskId') || '');
    const [record, script] = await Promise.all([latest(db, task.id), scriptContext(db, task.id)]);
    const source = splitSourceDescription(task.title);
    return response({ record, ready: Boolean(script), sourceHash: script?.hash || null,
      stale: Boolean(record && (!script || record.meta.source_hash !== script.hash)),
      sourceTitle: source.title, sourceTags: task.source_tags?.length ? task.source_tags : source.tags });
  } catch (error) { return failure(error); }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { db, task } = await context(request, String(body.taskId || ''));
    if (!['generate', 'save'].includes(body.action)) throw new RequestError('不支持的操作');
    const script = await scriptContext(db, task.id);
    if (!script) throw new RequestError('请先完成并确认改写文案', 409);
    if (body.sourceHash && body.sourceHash !== script.hash) throw new RequestError('确认稿已变化，请刷新后根据最新文案生成', 409);
    if (body.action === 'generate') {
      const key = process.env.DEEPSEEK_API_KEY;
      if (!key) throw new RequestError('发布文案服务缺少 DEEPSEEK_API_KEY 配置', 503);
      const source = splitSourceDescription(task.title);
      const result = await fetch('https://api.deepseek.com/chat/completions', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
        signal: AbortSignal.timeout(45_000),
        body: JSON.stringify({ model: 'deepseek-chat', temperature: 0.6, max_tokens: 2200, response_format: { type: 'json_object' }, messages: [
          { role: 'system', content: PUBLICATION_PROMPT },
          { role: 'user', content: JSON.stringify({ content_category: task.content_category, source_title: source.title, source_tags: task.source_tags || source.tags, confirmed_script: script.text }) },
        ] }),
      });
      if (!result.ok) throw new RequestError(`文案服务暂不可用（${result.status}），请稍后重试`, 502);
      const payload = await result.json();
      const raw = payload.choices?.[0]?.message?.content;
      if (typeof raw !== 'string') throw new RequestError('文案服务返回空内容，请重试', 502);
      let copy;
      try { copy = validatePublication(JSON.parse(raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, ''))); }
      catch (error) { throw new RequestError(`生成结果未满足要求：${error instanceof Error ? error.message : '格式错误'}。请重新生成`, 502); }
      // Recheck after the external request; an old draft must never masquerade as current.
      const current = await scriptContext(db, task.id);
      if (current?.hash !== script.hash) throw new RequestError('生成期间确认稿发生变化，请重新生成', 409);
      return response({ copy, sourceHash: script.hash, model: 'deepseek-chat' });
    }
    if (body.sourceHash !== script.hash) throw new RequestError('缺少有效的文案版本，请刷新后重试', 409);
    let copy;
    try { copy = validatePublication(body.copy); }
    catch (error) { throw new RequestError(error instanceof Error ? error.message : '发布文案格式无效'); }
    const previous = await latest(db, task.id);
    if ((previous?.id || null) !== (body.baseId || null)) throw new RequestError('发布文案已有新版本，请刷新并保留需要的修改', 409);
    const id = randomUUID();
    const { data: record, error } = await db.from('artifacts').insert({ id, task_id: task.id, stage_kind: 'render', type: 'publication_copy',
      storage_path: `${task.id}/publication/${id}`, meta: { copy, source_hash: script.hash, parent_id: previous?.id || null, schema_version: 1 } }).select('id,meta,created_at').single();
    if (error) throw new RequestError('发布文案保存失败，请重试', 503);
    return response({ record }, 201);
  } catch (error) { return failure(error); }
}

function failure(error: unknown) {
  if (error instanceof RequestError) return response({ error: error.message }, error.status);
  if (error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name)) return response({ error: '生成超时，原有文案仍保留，请重试' }, 504);
  return response({ error: error instanceof SyntaxError ? '请求格式无效' : error instanceof Error && error.message.includes('须为') ? error.message : '操作未完成，请稍后重试' }, 400);
}
