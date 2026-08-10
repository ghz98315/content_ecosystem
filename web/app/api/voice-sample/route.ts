import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

const BUCKET = "artifacts";
const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"]);

export async function POST(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return NextResponse.json({ error: "server misconfigured" }, { status: 500 });

  const form = await request.formData();
  const file = form.get("audio");
  if (!(file instanceof File)) return NextResponse.json({ error: "请选择音频文件" }, { status: 400 });
  if (!ALLOWED_TYPES.has(file.type.toLowerCase())) {
    return NextResponse.json({ error: "仅支持 MP3、WAV 或 M4A 音频" }, { status: 400 });
  }
  if (file.size > MAX_BYTES) return NextResponse.json({ error: "音频文件不能超过 10 MB" }, { status: 400 });

  const ext = file.name.split(".").pop()?.toLowerCase() || "mp3";
  const path = `voice-samples/${crypto.randomUUID()}.${ext}`;
  const sb = createClient(url, key);
  const upload = await sb.storage.from(BUCKET).upload(path, Buffer.from(await file.arrayBuffer()), {
    contentType: file.type || "audio/mpeg",
    upsert: false,
  });
  if (upload.error) return NextResponse.json({ error: upload.error.message }, { status: 500 });

  const signed = await sb.storage.from(BUCKET).createSignedUrl(path, 86400);
  if (signed.error || !signed.data?.signedUrl) {
    return NextResponse.json({ error: signed.error?.message || "生成下载链接失败" }, { status: 500 });
  }
  return NextResponse.json({ signedUrl: signed.data.signedUrl, path });
}
