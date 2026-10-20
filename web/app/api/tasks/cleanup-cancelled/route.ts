import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { cleanupCancelledTask } from '@/lib/cancelledTaskCleanup';

export const maxDuration = 60;

export async function POST(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  const token = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
  if (!url || !key) return NextResponse.json({ error: '服务配置缺失' }, { status: 500 });
  if (!token) return NextResponse.json({ error: '请先登录' }, { status: 401 });
  const db = createClient(url, key);
  const { data: auth, error: authError } = await db.auth.getUser(token);
  if (authError || !auth.user) return NextResponse.json({ error: '登录会话已失效' }, { status: 401 });
  try {
    const body = await request.json() as { taskIds?: unknown };
    const ids = Array.isArray(body.taskIds) ? body.taskIds : [];
    if (!ids.length || ids.length > 20 || ids.some(id => typeof id !== 'string'))
      return NextResponse.json({ error: '每次仅可清理 1 至 20 条任务' }, { status: 400 });
    const results = [];
    for (const id of new Set(ids as string[]))
      results.push({ id, ...await cleanupCancelledTask(db, id, auth.user.id) });
    return NextResponse.json({ results }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '清理失败' }, { status: 500 });
  }
}
