import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
  const key = process.env.SUPABASE_SERVICE_KEY!
  return createClient(url, key)
}

/* GET /api/xhs/books/[id] */
export async function GET(_: NextRequest, { params }: { params: { id: string } }) {
  const sb = getServiceClient()
  const { data, error } = await sb
    .from('xhs_books')
    .select('*')
    .eq('id', params.id)
    .single()
  if (error) return NextResponse.json({ error: error.message }, { status: 404 })
  return NextResponse.json(data)
}

/* PATCH /api/xhs/books/[id] — 更新品牌名等字段 */
export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const sb = getServiceClient()
  const body = await req.json()
  const allowed = ['title', 'brand_name']
  const updates = Object.fromEntries(
    Object.entries(body).filter(([k]) => allowed.includes(k))
  )
  const { data, error } = await sb
    .from('xhs_books')
    .update(updates)
    .eq('id', params.id)
    .select()
    .single()
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}
