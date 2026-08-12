import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

const BUCKET = "artifacts";
const MAX_BYTES = 500 * 1024 * 1024;

export async function POST(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;
  const bearer = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!url || !serviceKey || !bearer) return NextResponse.json({ error: "未登录或服务端未配置" }, { status: 401 });

  const auth = createClient(url, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "", {
    global: { headers: { Authorization: `Bearer ${bearer}` } },
  });
  const { data: userData, error: userError } = await auth.auth.getUser();
  if (userError || !userData.user) return NextResponse.json({ error: "登录会话已失效" }, { status: 401 });

  const form = await request.formData();
  const taskId = String(form.get("taskId") || "");
  const stageId = String(form.get("stageId") || "");
  const title = String(form.get("title") || "").trim();
  const author = String(form.get("author") || "").trim();
  const file = form.get("file");
  if (!(file instanceof File) || !taskId || !stageId) return NextResponse.json({ error: "缺少任务、阶段或上传文件" }, { status: 400 });
  if (!file.type.startsWith("audio/") && !file.type.startsWith("video/")) return NextResponse.json({ error: "仅支持视频或音频文件" }, { status: 400 });
  if (file.size > MAX_BYTES) return NextResponse.json({ error: "上传文件不能超过 500MB" }, { status: 400 });

  const sb = createClient(url, serviceKey);
  const { data: stage, error: stageError } = await sb.from("stages").select("id,params,task_id,tasks!inner(owner)").eq("id", stageId).eq("task_id", taskId).eq("kind", "ingest").single();
  const owner = (stage?.tasks as { owner?: string } | null)?.owner;
  if (stageError || !stage || owner !== userData.user.id) return NextResponse.json({ error: "无权上传到该任务" }, { status: 403 });

  const ext = file.name.split(".").pop()?.toLowerCase() || (file.type.startsWith("audio/") ? "mp3" : "mp4");
  const path = `${taskId}/manual.${ext}`;
  const upload = await sb.storage.from(BUCKET).upload(path, Buffer.from(await file.arrayBuffer()), { contentType: file.type, upsert: true });
  if (upload.error) return NextResponse.json({ error: upload.error.message }, { status: 500 });

  const { error: updateError } = await sb.from("stages").update({
    status: "pending", error: null,
    params: { ...(stage.params || {}), manual_file: path, manual_is_audio: file.type.startsWith("audio/"), manual_title: title || null, manual_author: author || null },
  }).eq("id", stageId);
  if (updateError) return NextResponse.json({ error: updateError.message }, { status: 500 });
  return NextResponse.json({ path });
}
