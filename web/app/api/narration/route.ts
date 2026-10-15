import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

async function context(request: Request, stageId: string) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const service = process.env.SUPABASE_SERVICE_KEY;
  const bearer = request.headers.get('authorization');
  if (!url || !anon || !service) throw new Error('服务配置缺失');
  if (!bearer?.startsWith('Bearer ')) throw new Error('请重新登录');
  const user = createClient(url, anon, { global: { headers: { Authorization: bearer } } });
  const { data: auth, error: authError } = await user.auth.getUser();
  if (authError || !auth.user) throw new Error('登录会话已失效');
  const { data: stage, error } = await user.from('stages').select('*').eq('id', stageId).eq('kind', 'tts').single();
  if (error || !stage) throw new Error('无权操作该配音阶段');
  const { data: task } = await user.from('tasks').select('owner').eq('id', stage.task_id).single();
  if (task?.owner !== auth.user.id) throw new Error('无权操作该任务');
  return { user, admin: createClient(url, service), stage };
}

export async function GET(request: NextRequest) {
  try {
    const { user, admin, stage } = await context(request, request.nextUrl.searchParams.get('stageId') || '');
    const { data: rewrite, error } = await user.from('stages').select('status,params').eq('task_id', stage.task_id).eq('kind', 'rewrite').single();
    if (error) throw new Error(error.message);
    const script = String(rewrite?.params?.final_text || '');
    const { data: versions, error: versionError } = await user.from('external_narrations').select('id,state,original_name,created_at').eq('stage_id', stage.id).order('created_at', { ascending: false }).limit(15);
    if (versionError) throw new Error(versionError.message);
    let current = null;
    let audioUrl: string | null = null;
    if (stage.params?.external_id) {
      const result = await user.from('external_narrations').select('*').eq('id', stage.params.external_id).eq('stage_id', stage.id).single();
      if (result.error) throw new Error(result.error.message);
      current = result.data;
      if (current.audio_path) {
        const signed = await admin.storage.from('artifacts').createSignedUrl(current.audio_path, 1800);
        if (signed.error) throw new Error(signed.error.message);
        audioUrl = signed.data.signedUrl;
      }
    }
    return NextResponse.json({ stage, script, rewriteReady: rewrite?.status === 'done', current, versions, audioUrl }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '读取配音失败' }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { user, admin, stage } = await context(request, String(body.stageId || ''));
    const name = String(body.name || '');
    const extension = name.split('.').pop()?.toLowerCase();
    const size = Number(body.size);
    if (!['wav', 'mp3'].includes(extension || '') || !Number.isSafeInteger(size) || size <= 0 || size > 200 * 1024 * 1024) {
      throw new Error('请上传不超过 200MB 的 WAV 或 MP3');
    }
    const prepared = await user.rpc('narration_action', { p_stage_id: stage.id, p_action: 'prepare', p_data: { name, extension, size } });
    if (prepared.error) throw new Error(prepared.error.message);
    const version = prepared.data;
    const signed = await admin.storage.from('artifacts').createSignedUploadUrl(version.original_path);
    if (signed.error) throw new Error(signed.error.message);
    return NextResponse.json({ id: version.id, path: version.original_path, token: signed.data.token });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '准备上传失败' }, { status: 400 });
  }
}

export async function PATCH(request: Request) {
  try {
    const body = await request.json();
    const { user, stage } = await context(request, String(body.stageId || ''));
    const action = String(body.action || '');
    if (!['source', 'submit', 'realign', 'approve'].includes(action)) throw new Error('未知操作');
    // All publication/state changes use the caller's identity and a DB transaction.
    const result = await user.rpc('narration_action', { p_stage_id: stage.id, p_action: action, p_data: body.data || {} });
    if (result.error) throw new Error(result.error.message);
    return NextResponse.json(result.data);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '更新配音失败' }, { status: 409 });
  }
}
