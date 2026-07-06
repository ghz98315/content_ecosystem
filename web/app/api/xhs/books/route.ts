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

/* POST /api/xhs/books — 新建书籍（文字或 PDF）*/
export async function POST(req: NextRequest) {
  const sb = getServiceClient()
  const contentType = req.headers.get('content-type') ?? ''

  let title = '', brandName = '大厂工程爸', rawText = '', fileUrl = ''

  if (contentType.includes('multipart/form-data')) {
    // PDF 上传路径
    const form = await req.formData()
    title     = String(form.get('title') ?? '')
    brandName = String(form.get('brand_name') ?? '大厂工程爸')
    const file = form.get('file') as File | null

    if (file) {
      // 服务端解析 PDF
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const pdfParse = require('pdf-parse') as (buf: Buffer) => Promise<{ text: string }>
      const arrayBuffer = await file.arrayBuffer()
      const buffer = Buffer.from(arrayBuffer)
      const parsed = await pdfParse(buffer)
      rawText = parsed.text

      // 上传原 PDF 到 Supabase Storage
      const path = `xhs/${Date.now()}-${file.name}`
      const { error: uploadErr } = await sb.storage
        .from('artifacts')
        .upload(path, buffer, { contentType: 'application/pdf' })
      if (!uploadErr) fileUrl = path
    }
  } else {
    // 纯文字路径
    const body = await req.json()
    title     = body.title ?? ''
    brandName = body.brand_name ?? '大厂工程爸'
    rawText   = body.raw_text ?? ''
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
