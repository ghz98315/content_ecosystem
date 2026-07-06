"use client";
import { useState } from 'react'

interface Topic {
  id: string
  book_id: string
  title: string
  pain_point: string
  logic: string
  created_at: string
}

interface Props {
  book: { id: string; raw_text: string | null }
  selectedText: string
  onGoToCopy: (topic: Topic) => void
  onGoToCards: (topic: Topic) => void
}

const BANNED = ['私信','留言','送资料','链接','加群','求关注','求收藏']

export function TopicsTab({ book, selectedText, onGoToCopy, onGoToCards }: Props) {
  const [painPoint, setPainPoint] = useState('')
  const [topics, setTopics] = useState<Topic[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const generate = async () => {
    if (!selectedText.trim()) { setError('请先在「内容选取」Tab 选择段落'); return }
    setError(''); setLoading(true)
    try {
      const res = await fetch('/api/xhs/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: book.id, pain_point: painPoint, selected_text: selectedText }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error ?? '生成失败'); return }
      setTopics(prev => [...data.topics, ...prev])
      setSelected(new Set(data.topics.map((t: Topic) => t.id)))
    } catch {
      setError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  const startEdit = (t: Topic) => { setEditingId(t.id); setEditTitle(t.title) }

  const saveEdit = async (id: string) => {
    setTopics(prev => prev.map(t => t.id === id ? { ...t, title: editTitle } : t))
    setEditingId(null)
    await fetch(`/api/xhs/topics/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: editTitle }),
    })
  }

  const warnBanned = (text: string) => BANNED.find(w => text.includes(w))

  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      {/* 生成区 */}
      <div className="bg-white rounded-2xl border border-xhs-border p-6 mb-6">
        <h3 className="font-semibold text-xhs-primary mb-4">AI 生成爆款选题</h3>
        <div className="flex gap-3">
          <input
            className="xhs-input flex-1"
            placeholder="输入核心痛点（可选，留空则 AI 自动分析）"
            value={painPoint}
            onChange={e => setPainPoint(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && generate()}
          />
          <button onClick={generate} disabled={loading} className="xhs-btn-primary min-w-28 flex items-center gap-2">
            {loading
              ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />生成中…</>
              : '✨ AI 生成选题'}
          </button>
        </div>
        {selectedText.length > 0 && (
          <p className="text-xs text-xhs-muted mt-2">
            基于已选 {selectedText.length.toLocaleString()} 字内容生成
          </p>
        )}
        {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg mt-3">{error}</p>}
      </div>

      {/* 选题卡片列表 */}
      {topics.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="text-4xl mb-4">📌</div>
          <p className="text-sm text-xhs-muted">点击「AI 生成选题」生成爆款选题</p>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-xhs-muted">共 {topics.length} 个选题，已选 {selected.size} 个</p>
            <button
              onClick={() => setSelected(selected.size === topics.length ? new Set() : new Set(topics.map(t => t.id)))}
              className="xhs-btn-ghost py-1 px-3 text-xs"
            >
              {selected.size === topics.length ? '取消全选' : '全选'}
            </button>
          </div>

          <div className="space-y-4">
            {topics.map(topic => {
              const isSelected = selected.has(topic.id)
              const warn = warnBanned(topic.title + topic.logic)
              return (
                <div key={topic.id}
                  className={`bg-white rounded-2xl border-2 p-5 transition-all ${
                    isSelected ? 'border-xhs-accent/50' : 'border-xhs-border'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(topic.id)}
                      className="mt-1 w-4 h-4 accent-[#FF6B35] flex-shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      {/* 标题（内联编辑）*/}
                      {editingId === topic.id ? (
                        <div className="flex gap-2 mb-2">
                          <input
                            className="xhs-input flex-1 text-base font-semibold py-1"
                            value={editTitle}
                            onChange={e => setEditTitle(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') saveEdit(topic.id); if (e.key === 'Escape') setEditingId(null) }}
                            autoFocus
                          />
                          <button onClick={() => saveEdit(topic.id)} className="xhs-btn-primary py-1 px-3 text-xs">保存</button>
                          <button onClick={() => setEditingId(null)} className="xhs-btn-ghost py-1 px-3 text-xs">取消</button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 mb-2">
                          <h4 className="font-semibold text-xhs-primary text-base">{topic.title}</h4>
                          <button onClick={() => startEdit(topic)} className="text-xhs-muted hover:text-xhs-accent text-xs px-1.5 py-0.5 rounded hover:bg-orange-50 transition-colors">
                            ✏️ 编辑
                          </button>
                          {warn && <span className="text-xs text-red-500 bg-red-50 px-2 py-0.5 rounded-full">⚠️ 含违规词</span>}
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-xs text-xhs-muted font-medium">核心痛点</span>
                          <p className="text-xhs-text mt-0.5">{topic.pain_point}</p>
                        </div>
                        <div>
                          <span className="text-xs text-xhs-muted font-medium">内容逻辑</span>
                          <p className="text-xhs-text mt-0.5">{topic.logic}</p>
                        </div>
                      </div>

                      <div className="flex gap-2 mt-4">
                        <button onClick={() => onGoToCopy(topic)} className="xhs-btn-primary py-1.5 px-4 text-xs">
                          ✍️ 去生成文案
                        </button>
                        <button onClick={() => onGoToCards(topic)} className="xhs-btn-ghost py-1.5 px-4 text-xs">
                          🎨 去生成卡片
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
