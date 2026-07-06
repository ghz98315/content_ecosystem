import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
  const key = process.env.SUPABASE_SERVICE_KEY!
  return createClient(url, key)
}

const BANNED_WORDS = ['私信','留言','送资料','买','链接','加群','求关注','求收藏']

const STYLE_PROMPTS: Record<string, string> = {
  engineer:  '理性、克制、一针见血、有降维打击感，像大厂工程师爸爸在写笔记',
  emotional: '情绪共鸣，贴近读者痛点，有温度，语气亲切',
  practical: '纯干货实操，条理清晰，多用数字和步骤',
}

/* POST /api/xhs/copy */
export async function POST(req: NextRequest) {
  const { topic_id, title, knowledge, style = 'engineer' } = await req.json()
  if (!title) return NextResponse.json({ error: 'title 必填' }, { status: 400 })

  const styleDesc = STYLE_PROMPTS[style] ?? STYLE_PROMPTS.engineer

  // 调用 DeepSeek（OpenAI 兼容协议）
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
          content: `你是大厂工程师爸爸，正在写小红书笔记。文风：${styleDesc}。
合规红线（绝对禁止）：${BANNED_WORDS.join('、')} 等任何引流诱导词汇。`,
        },
        {
          role: 'user',
          content: `标题：${title}
核心知识点：${knowledge ?? '请根据标题自行发挥'}

写作结构：
1. 痛点场景引入
2. 揭露假象（态度问题其实是认知问题）
3. 大厂解决方案（如5-Why、防呆设计等）
4. 价值升华收尾

附加任务：额外生成2条评论区剧本（1条小号提问+1条大号专业回复）。

返回严格JSON：
{"body":"正文markdown内容","comments":[{"role":"小号","content":""},{"role":"大号","content":""}]}`,
        },
      ],
    }),
  })

  if (!res.ok) {
    const err = await res.text()
    return NextResponse.json({ error: `DeepSeek API 错误: ${err}` }, { status: 500 })
  }

  const json = await res.json()
  let result: { body: string; comments: Array<{ role: string; content: string }> }
  try {
    // 去掉 DeepSeek 偶尔在 json_object 模式下包裹的 ```json ... ``` markdown 块
    const raw = json.choices[0].message.content.replace(/^```json\s*/i, '').replace(/\s*```$/, '').trim()
    result = JSON.parse(raw)
  } catch {
    const preview = json.choices[0]?.message?.content?.slice(0, 200) ?? '(empty)'
    return NextResponse.json({ error: `解析 LLM 返回失败: ${preview}` }, { status: 500 })
  }

  // 合规检测：软警告，不拦截，返回 banned_word 让前端标红
  const hitWord = BANNED_WORDS.find(w => result.body.includes(w))

  // 存库
  const sb = getServiceClient()
  const { data, error } = await sb.from('xhs_drafts').insert({
    topic_id: topic_id ?? null,
    style,
    body:     result.body,
    comments: result.comments,
  }).select().single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ...data, banned_word: hitWord ?? null }, { status: 201 })
}
