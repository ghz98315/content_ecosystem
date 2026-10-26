import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";
import { MUSIC_PRESET_PATHS } from "@/lib/musicPresets";

const BUCKET = "artifacts";

export async function GET(req: NextRequest) {
  const path = req.nextUrl.searchParams.get("path");
  if (!path) return NextResponse.json({ error: "missing path" }, { status: 400 });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key)
    return NextResponse.json({ error: "server misconfigured" }, { status: 500 });

  const sb = createClient(url, key);
  {
    const token = req.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
    if (!token) return NextResponse.json({ error: '请先登录' }, { status: 401 });
    const { data: auth } = await sb.auth.getUser(token);
    if (!auth.user) return NextResponse.json({ error: '登录会话已失效' }, { status: 401 });
    if (path.includes('\\') || path.split('/').some(part => !part || part === '..' || part === '.'))
      return NextResponse.json({ error: '无效的素材路径' }, { status: 400 });
    const prefix = path.split('/')[0];
    if (MUSIC_PRESET_PATHS.has(path)) {
      // The six licensed library tracks are shared, read-only preset assets.
    } else if (prefix === 'voice-samples') {
      const { data: profile } = await sb.from('voice_profiles').select('id').eq('owner',auth.user.id).eq('sample_path',path).limit(1);
      if (path.split('/')[1] !== auth.user.id && !profile?.length)
        return NextResponse.json({error:'无权读取该音色样本'},{status:403});
    } else {
      if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(prefix))
        return NextResponse.json({error:'无权读取该素材'},{status:403});
      const { data: task } = await sb.from('tasks').select('owner').eq('id', prefix).eq('owner',auth.user.id).maybeSingle();
      if (!task) return NextResponse.json({ error: '无权读取该任务素材' }, { status: 403 });
    }
  }
  const requestedName = req.nextUrl.searchParams.get('download');
  const downloadName = requestedName?.replace(/[\\/:*?"<>|\r\n]/g, '_').slice(0, 120);
  const { data, error } = await sb.storage.from(BUCKET).createSignedUrl(
    path, 300, downloadName ? { download: downloadName } : undefined,
  );
  if (error || !data?.signedUrl)
    return NextResponse.json({ error: error?.message ?? "signed url failed" }, { status: 404 });

  const signedUrl = new URL(data.signedUrl);
  const version = req.nextUrl.searchParams.get('version');
  if (version) signedUrl.searchParams.set('cacheNonce', version.slice(0, 128));
  return NextResponse.json({ signedUrl: signedUrl.toString() },{headers:{'Cache-Control':'no-store'}});
}
