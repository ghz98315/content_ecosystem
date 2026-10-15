import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const BUCKET = "artifacts";

export async function GET(req: NextRequest) {
  const path = req.nextUrl.searchParams.get("path");
  if (!path) return NextResponse.json({ error: "missing path" }, { status: 400 });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key)
    return NextResponse.json({ error: "server misconfigured" }, { status: 500 });

  const sb = createClient(url, key);
  if (path.includes('/external/')) {
    const token = req.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
    if (!token) return NextResponse.json({ error: '请先登录' }, { status: 401 });
    const { data: auth } = await sb.auth.getUser(token);
    if (!auth.user) return NextResponse.json({ error: '登录会话已失效' }, { status: 401 });
    const { data: task } = await sb.from('tasks').select('owner').eq('id', path.split('/')[0]).single();
    if (!task || task.owner !== auth.user.id) return NextResponse.json({ error: '无权读取配音' }, { status: 403 });
  }
  const { data, error } = await sb.storage.from(BUCKET).createSignedUrl(path, 300);
  if (error || !data?.signedUrl)
    return NextResponse.json({ error: error?.message ?? "signed url failed" }, { status: 404 });

  return NextResponse.json({ signedUrl: data.signedUrl });
}
