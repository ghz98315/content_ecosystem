"use client";
import { useState } from 'react'

interface Topic {
  id: string
  title: string
  pain_point: string
}

interface Draft {
  id: string
  body: string
  comments: Array<{ role: string; content: string }>
}

interface Props {
  book: { id: string }
  selectedText: string
  initialTopic?: Topic | null
}

const BANNED = ['私信','留言','送资料','链接','加群','求关注','求收藏']
const STYLES = [
  { value: 'engineer',  label: '大厂降维打击风' },
  { value: 'emotional', label: '情绪共鸣风' },
  { value: 'practical', label: '纯干货实操风' },
]

export function CopyTab({ book, selectedText, initialTopic }: Props) {
  const [title, setTitle]       = useState(initialTopic?.title ?? '')
  const [knowledge, setKnowledge] = useState(initialTopic?.pain_point ?? '')
  const [style, setStyle]       = useState('engineer')
  const [draft, setDraft]       = useState<Draft | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [copied, setCopied]     = useState<'body' | 'comment' | null>(null)

  const generate = async () => {
    if (!title.trim()) { setError('请填写标题'); return }
    setError(''); setLoading(true)
    try {
      const res = await fetch('/api/xhs/copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, knowledge, style }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error ?? '生成失败'); return }
      setDraft(data)
    } catch {
      setError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  const copy = async (text: string, type: 'body' | 'comment') => {
    await navigator.clipboard.writeText(text)
    setCopied(type)
    setTimeout(() => setCopied(null), 2000)
  }

  const bodyBanned = draft ? BANNED.find(w => draft.body.includes(w)) : null

  return (
    <div className="flex gap-6 h-full p-8 max-w-6xl mx-auto">
      {/* 左侧：参数区 */}
      <div className="w-80 flex-shrink-0 space-y-5">
        <div className="bg-white rounded-2xl border border-xhs-border p-5 space-y-4">
          <h3 className="font-semibold text-xhs-primary">创作参数</h3>

          <div>
            <label className="xhs-section-title block">笔记标题</label>
            <input
              className="xhs-input"
              placeholder="例：大厂爸爸的除错笔记"
              value={title}
              onChange={e => setTitle(e.target.value)}
            />
          </div>

          <div>
            <label className="xhs-section-title block">核心知识点</label>
            <textarea
              className="xhs-textarea h-28"
              placeholder="粘贴关键段落，或留空让 AI 基于标题发挥…"
              value={knowledge}
              onChange={e => setKnowledge(e.target.value)}
            />
            {selectedText && !knowledge && (
              <button
                onClick={() => setKnowledge(selectedText.slice(0, 500))}
                className="text-xs text-xhs-accent hover:underline mt-1"
              >
                从已选内容导入前 500 字
              </button>
            )}
          </div>

          <div>
            <label className="xhs-section-title block">文风</label>
            <div className="space-y-2">
              {STYLES.map(s => (
                <label key={s.value} className={`flex items-center gap-2 p-2.5 rounded-xl border cursor-pointer transition-all ${
                  style === s.value ? 'border-xhs-accent bg-orange-50' : 'border-xhs-border hover:border-xhs-accent/40'
                }`}>
                  <input type="radio" name="style" value={s.value} checked={style === s.value}
                    onChange={() => setStyle(s.value)} className="accent-[#FF6B35]" />
                  <span className="text-sm text-xhs-text">{s.label}</span>
                </label>
              ))}
            </div>
          </div>

          <button onClick={generate} disabled={loading} className="xhs-btn-primary w-full flex items-center justify-center gap-2">
            {loading
              ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />生成中…</>
              : '🚀 一键生成文案'}
          </button>

          {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
        </div>
      </div>

      {/* 右侧：结果区 */}
      <div className="flex-1 min-w-0 space-y-5">
        {!draft ? (
          <div className="bg-white rounded-2xl border border-xhs-border flex flex-col items-center justify-center py-24 text-center">
            <div className="text-4xl mb-4">✍️</div>
            <p className="text-sm text-xhs-muted">填写参数后点击「一键生成文案」</p>
          </div>
        ) : (
          <>
            {/* 正文 */}
            <div className="bg-white rounded-2xl border border-xhs-border p-5">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold text-xhs-primary">📝 正文</h4>
                <div className="flex items-center gap-2">
                  {bodyBanned && (
                    <span className="text-xs text-red-500 bg-red-50 px-2 py-1 rounded-full">⚠️ 含违规词：{bodyBanned}</span>
                  )}
                  <button onClick={() => copy(draft.body, 'body')} className="xhs-btn-ghost py-1 px-3 text-xs">
                    {copied === 'body' ? '✓ 已复制' : '复制'}
                  </button>
                </div>
              </div>
              <div className="prose prose-sm max-w-none text-xhs-text leading-relaxed whitespace-pre-wrap border-l-4 border-xhs-accent pl-4 text-sm">
                {draft.body}
              </div>
            </div>

            {/* 评论剧本 */}
            <div className="bg-white rounded-2xl border border-xhs-border p-5">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold text-xhs-primary">💬 评论区剧本</h4>
                <button
                  onClick={() => copy(draft.comments.map(c => `【${c.role}】${c.content}`).join('\n\n'), 'comment')}
                  className="xhs-btn-ghost py-1 px-3 text-xs"
                >
                  {copied === 'comment' ? '✓ 已复制' : '复制'}
                </button>
              </div>
              <div className="space-y-3">
                {draft.comments.map((c, i) => (
                  <div key={i} className={`rounded-xl p-3 ${
                    c.role === '小号' ? 'bg-gray-50 border border-xhs-border' : 'bg-orange-50 border border-xhs-accent/20'
                  }`}>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full mr-2 ${
                      c.role === '小号' ? 'bg-gray-200 text-gray-600' : 'bg-xhs-accent text-white'
                    }`}>{c.role}</span>
                    <span className="text-sm text-xhs-text">{c.content}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
