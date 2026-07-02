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
  const { data, error } = await sb.storage.from(BUCKET).createSignedUrl(path, 300);
  if (error || !data?.signedUrl)
    return NextResponse.json({ error: error?.message ?? "signed url failed" }, { status: 404 });

  return NextResponse.json({ signedUrl: data.signedUrl });
}
