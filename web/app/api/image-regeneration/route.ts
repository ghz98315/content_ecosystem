import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

const BUCKET = "artifacts";

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const stageId = String(body.stageId || "");
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    const serviceKey = process.env.SUPABASE_SERVICE_KEY;
    const bearer = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
    if (!url || !anonKey || !serviceKey || !bearer || !stageId) throw new Error("未登录或缺少图片阶段信息");

    const userClient = createClient(url, anonKey, { global: { headers: { Authorization: `Bearer ${bearer}` } } });
    const { data: userData } = await userClient.auth.getUser();
    if (!userData.user) throw new Error("登录会话已失效");

    const service = createClient(url, serviceKey);
    const { data: stage, error: stageError } = await service
      .from("stages")
      .select("task_id,tasks!inner(owner)")
      .eq("id", stageId)
      .eq("kind", "image")
      .single();
    const owner = (stage?.tasks as { owner?: string } | null)?.owner;
    if (stageError || !stage || owner !== userData.user.id) throw new Error("无权操作该图片任务");

    const { data: artifacts, error: artifactError } = await service
      .from("artifacts")
      .select("storage_path")
      .eq("task_id", stage.task_id)
      .in("stage_kind", ["image", "render"]);
    if (artifactError) throw new Error(artifactError.message);
    const paths = (artifacts || []).map(item => item.storage_path).filter(Boolean);
    if (paths.length) {
      const { error: removeError } = await service.storage.from(BUCKET).remove(paths);
      if (removeError) throw new Error(`删除旧图片失败：${removeError.message}`);
    }

    const { data, error } = await userClient.rpc("regenerate_image_stage", { p_stage_id: stageId });
    if (error || !data?.length) throw new Error(error?.message || "重置图片阶段失败");
    return NextResponse.json({ stages: data, deleted: paths.length });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "全量重新生成失败" }, { status: 400 });
  }
}
