import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

const BUCKET = "artifacts";
const MAX_BYTES = 500 * 1024 * 1024;

async function authorizedStage(request: Request, body: Record<string, unknown>) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;
  const bearer = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  const taskId = String(body.taskId || "");
  const stageId = String(body.stageId || "");
  if (!url || !serviceKey || !bearer || !taskId || !stageId) throw new Error("未登录或缺少任务信息");
  const auth = createClient(url, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "", { global: { headers: { Authorization: `Bearer ${bearer}` } } });
  const { data: userData } = await auth.auth.getUser();
  if (!userData.user) throw new Error("登录会话已失效");
  const sb = createClient(url, serviceKey);
  const { data: stage, error } = await sb.from("stages").select("id,params,task_id,tasks!inner(owner)").eq("id", stageId).eq("task_id", taskId).eq("kind", "ingest").single();
  const owner = (stage?.tasks as { owner?: string } | null)?.owner;
  if (error || !stage || owner !== userData.user.id) throw new Error("无权操作该任务");
  return { sb, stage, taskId, stageId };
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const { sb, taskId } = await authorizedStage(request, body);
    const size = Number(body.size || 0);
    const mime = String(body.mime || "");
    const ext = String(body.name || "").split(".").pop()?.toLowerCase() || (mime.startsWith("audio/") ? "mp3" : "mp4");
    if (!mime.startsWith("audio/") && !mime.startsWith("video/")) return NextResponse.json({ error: "仅支持视频或音频文件" }, { status: 400 });
    if (!Number.isFinite(size) || size <= 0 || size > MAX_BYTES) return NextResponse.json({ error: "上传文件必须小于 500MB" }, { status: 400 });
    const path = `${taskId}/manual.${ext}`;
    const { data, error } = await sb.storage.from(BUCKET).createSignedUploadUrl(path, { upsert: true });
    if (error || !data?.token) return NextResponse.json({ error: error?.message || "创建上传授权失败" }, { status: 500 });
    return NextResponse.json({ path, token: data.token });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "创建上传授权失败" }, { status: 401 });
  }
}

export async function PATCH(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const { sb, stage, stageId } = await authorizedStage(request, body);
    const path = String(body.path || "");
    const mime = String(body.mime || "");
    if (!path || !path.startsWith(`${stage.task_id}/manual.`)) return NextResponse.json({ error: "上传路径无效" }, { status: 400 });
    const { error } = await sb.from("stages").update({
      status: "pending", error: null,
      params: { ...(stage.params || {}), manual_file: path, manual_is_audio: mime.startsWith("audio/"), manual_title: String(body.title || "").trim() || null, manual_author: String(body.author || "").trim() || null },
    }).eq("id", stageId);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ path });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "确认上传失败" }, { status: 401 });
  }
}
