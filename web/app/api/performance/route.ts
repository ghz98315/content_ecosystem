import { createClient } from '@supabase/supabase-js';
import { NextRequest, NextResponse } from 'next/server';
import { importSnapshots } from '@/lib/performanceImportServer';

export const dynamic = 'force-dynamic';
const PLATFORMS = new Set(['douyin', 'kuaishou', 'xiaohongshu', 'shipinhao', 'bilibili', 'other']);
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

async function context(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  const token = request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/i)?.[1];
  if (!url || !key) throw new Error('服务配置缺失');
  if (!token) return null;
  const db = createClient(url, key);
  const { data, error } = await db.auth.getUser(token);
  if (error || !data.user) return null;
  return { db, owner: data.user.id };
}

function badRequest(message: string) { return NextResponse.json({ error: message }, { status: 400 }); }
function nonnegative(value: unknown): number | null {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}

export async function GET(request: NextRequest) {
  try {
    const auth = await context(request);
    if (!auth) return NextResponse.json({ error: '请先登录' }, { status: 401 });
    const { data: posts, error } = await auth.db.from('published_posts')
      .select('id,task_id,platform,title,post_url,published_at,created_at')
      .eq('owner', auth.owner).order('published_at', { ascending: false }).limit(500);
    if (error) throw error;
    const ids = (posts || []).map(post => post.id);
    const { data: metrics, error: metricsError } = ids.length
      ? await auth.db.from('published_post_metrics')
        .select('id,post_id,recorded_at,views,likes,comments,shares,saves,follows,notes')
        .in('post_id', ids).order('recorded_at', { ascending: false }).limit(5000)
      : { data: [], error: null };
    if (metricsError) throw metricsError;
    return NextResponse.json({ posts, metrics, truncated: (posts?.length || 0) === 500 || (metrics?.length || 0) === 5000 },
      { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '数据读取失败' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const auth = await context(request);
    if (!auth) return NextResponse.json({ error: '请先登录' }, { status: 401 });
    const body = await request.json();
    if (body.action === 'metric_import') {
      try { return NextResponse.json(await importSnapshots(auth.db, auth.owner, body.rows)); }
      catch (error) { return badRequest(error instanceof Error ? error.message : '导入失败'); }
    }
    if (body.action === 'post') {
      if (!UUID.test(body.taskId || '') || !PLATFORMS.has(body.platform)) return badRequest('任务或平台无效');
      const { data: task } = await auth.db.from('tasks').select('id,title').eq('id', body.taskId).eq('owner', auth.owner).maybeSingle();
      if (!task) return NextResponse.json({ error: '无权访问该任务' }, { status: 403 });
      const publishedAt = new Date(body.publishedAt);
      if (Number.isNaN(publishedAt.getTime()) || publishedAt.getTime() > Date.now() + 86400000) return badRequest('发布时间无效');
      const postUrl = String(body.postUrl || '').trim();
      if (postUrl && (!/^https:\/\//i.test(postUrl) || postUrl.length > 2000)) return badRequest('请输入 HTTPS 作品链接');
      const title = String(body.title || task.title || '').trim().slice(0, 200);
      const { data, error } = await auth.db.from('published_posts').insert({
        owner: auth.owner, task_id: task.id, platform: body.platform, title,
        post_url: postUrl || null, published_at: publishedAt.toISOString(),
      }).select('id').single();
      if (error) throw error;
      return NextResponse.json({ id: data.id }, { status: 201 });
    }
    if (body.action === 'metric') {
      if (!UUID.test(body.postId || '')) return badRequest('作品无效');
      const { data: post } = await auth.db.from('published_posts').select('id').eq('id', body.postId).eq('owner', auth.owner).maybeSingle();
      if (!post) return NextResponse.json({ error: '无权访问该作品' }, { status: 403 });
      const fields = ['views', 'likes', 'comments', 'shares', 'saves', 'follows'] as const;
      const values: Record<string, number> = {};
      for (const field of fields) {
        const value = nonnegative(body[field]);
        if (value === null) return badRequest(`${field} 必须为非负整数`);
        values[field] = value;
      }
      const notes = String(body.notes || '').trim().slice(0, 500);
      const { data, error } = await auth.db.from('published_post_metrics')
        .insert({ post_id: post.id, ...values, notes }).select('id').single();
      if (error) throw error;
      return NextResponse.json({ id: data.id }, { status: 201 });
    }
    return badRequest('操作无效');
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '保存失败' }, { status: 500 });
  }
}
