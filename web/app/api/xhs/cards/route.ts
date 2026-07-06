import { NextRequest, NextResponse } from 'next/server'

const BANNED_WORDS = ['私信','留言','送资料','买','链接','加群','求关注','求收藏','求点赞']

/* POST /api/xhs/cards */
export async function POST(req: NextRequest) {
  const { content, title } = await req.json()
  if (!content) return NextResponse.json({ error: 'content 必填' }, { status: 400 })

  const res = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.DEEPSEEK_API_KEY}`,
    },
    body: JSON.stringify({
      model: 'deepseek-chat',
      response_format: { type: 'json_object' },
      messages: [
        {
          role: 'system',
          content: `你是专业的小红书内容排版师。合规红线：绝对禁止 ${BANNED_WORDS.join('、')} 等引流词汇。`,
        },
        {
          role: 'user',
          content: `标题：${title ?? ''}
原文内容：
${content}

任务：
1. 将原文按逻辑切分为 3-5 段，每段字数适合放在一张 3:4 卡片阅读（约 100-200 字）
2. 生成一段价值总结（2-3句话）
3. 生成一个合规互动问题（纯探讨式，禁止引流）

返回严格JSON：{"pages":["段落1","段落2","..."],"summary":"价值总结","cta":"互动提问"}`,
        },
      ],
    }),
  })

  if (!res.ok) {
    return NextResponse.json({ error: 'DeepSeek API 错误' }, { status: 500 })
  }

  const json = await res.json()
  let result: { pages: string[]; summary: string; cta: string }
  try {
    result = JSON.parse(json.choices[0].message.content)
  } catch {
    return NextResponse.json({ error: '解析 LLM 返回失败' }, { status: 500 })
  }

  // 合规检测
  const allText = [...result.pages, result.summary, result.cta].join('')
  const hit = BANNED_WORDS.find(w => allText.includes(w))
  if (hit) return NextResponse.json({ error: `违规词汇：${hit}` }, { status: 422 })

  return NextResponse.json(result)
}
