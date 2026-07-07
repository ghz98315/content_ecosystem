import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
  const key = process.env.SUPABASE_SERVICE_KEY!
  return createClient(url, key)
}

/* GET /api/xhs/books — 列出所有书籍 */
export async function GET() {
  const sb = getServiceClient()
  const { data, error } = await sb
    .from('xhs_books')
    .select('*')
    .order('created_at', { ascending: false })
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}

/* POST /api/xhs/books — 新建书籍（文字 或 PDF via storage path）*/
export async function POST(req: NextRequest) {
  const sb = getServiceClient()

  // 统一走 JSON，PDF 已由客户端直传 Storage，这里只接收 file_path
  const body = await req.json()
  let title     = body.title ?? ''
  let brandName = body.brand_name ?? '大厂工程爸'
  let rawText   = body.raw_text ?? ''
  const fileUrl = body.file_path ?? ''

  if (fileUrl) {
    // 从 Supabase Storage 下载并解析 PDF
    const { data: fileData, error: dlErr } = await sb.storage
      .from('artifacts')
      .download(fileUrl)
    if (dlErr) return NextResponse.json({ error: `下载 PDF 失败：${dlErr.message}` }, { status: 500 })

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const pdfParse = require('pdf-parse') as (buf: Buffer) => Promise<{ text: string }>
    const buffer = Buffer.from(await fileData.arrayBuffer())
    const parsed = await pdfParse(buffer)
    rawText = parsed.text
  }

  if (!title.trim()) {
    return NextResponse.json({ error: '书名不能为空' }, { status: 400 })
  }

  const { data, error } = await sb
    .from('xhs_books')
    .insert({ title, brand_name: brandName, raw_text: rawText, file_url: fileUrl })
    .select()
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data, { status: 201 })
}
