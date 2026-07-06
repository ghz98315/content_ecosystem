import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'
import OpenAI from 'openai'

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
  const key = process.env.SUPABASE_SERVICE_KEY!
  return createClient(url, key)
}

const BANNED_WORDS = ['私信','留言','送资料','买','链接','加群','求关注','点赞','求收藏']

/* POST /api/xhs/topics — 调用 OpenAI 生成选题 */
export async function POST(req: NextRequest) {
  const { book_id, pain_point, selected_text } = await req.json()
  if (!book_id) return NextResponse.json({ error: 'book_id 必填' }, { status: 400 })

  const sb = getServiceClient()

  // 优先使用前端传来的已选段落，否则从 DB 取前 800 字
  let context = (selected_text ?? '').slice(0, 1000)
  if (!context) {
    const { data: book } = await sb
      .from('xhs_books').select('raw_text').eq('id', book_id).single()
    context = (book?.raw_text ?? '').slice(0, 800)
  }

  const openai = new OpenAI({
    apiKey: process.env.DEEPSEEK_API_KEY,
    baseURL: 'https://api.deepseek.com',
  })

  const completion = await openai.chat.completions.create({
    model: 'deepseek-chat',
    response_format: { type: 'json_object' },
    messages: [
      {
        role: 'system',
        content: '你是一个小红书爆款操盘手。严格遵守合规红线：禁止输出任何引流词汇（私信/留言/送资料/买/链接/加群等）。',
      },
      {
        role: 'user',
        content: `核心痛点：${pain_point || '待分析'}
书籍内容摘要：${context}

请生成3个爆款小红书选题：
- 标题≤20字，要有大厂降维打击感，可含emoji
- 返回严格JSON：{"topics":[{"title":"","painPoint":"","logic":""}]}`,
      },
    ],
  })

  let topics: Array<{ title: string; painPoint: string; logic: string }> = []
  try {
    const raw = (completion.choices[0].message.content ?? '{}').replace(/^```json\s*/i, '').replace(/\s*```$/, '').trim()
    const parsed = JSON.parse(raw)
    topics = parsed.topics ?? []
  } catch {
    return NextResponse.json({ error: '解析 LLM 返回失败' }, { status: 500 })
  }

  // 合规检测
  for (const t of topics) {
    const hit = BANNED_WORDS.find(w => t.title.includes(w) || t.logic.includes(w))
    if (hit) return NextResponse.json({ error: `违规词汇：${hit}` }, { status: 422 })
  }

  // 存库
  const rows = topics.map(t => ({
    book_id,
    title:      t.title,
    pain_point: t.painPoint,
    logic:      t.logic,
  }))
  const { data, error } = await sb.from('xhs_topics').insert(rows).select()
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  return NextResponse.json({ topics: data }, { status: 201 })
}
