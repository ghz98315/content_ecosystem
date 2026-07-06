"use client";
export const dynamic = "force-dynamic";

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'

interface XhsBook {
  id: string
  title: string
  brand_name: string
  raw_text: string | null
  file_url: string | null
  created_at: string
}

export default function XhsPage() {
  const [books, setBooks] = useState<XhsBook[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)

  const loadBooks = async () => {
    const { data } = await supabase
      .from('xhs_books')
      .select('*')
      .order('created_at', { ascending: false })
    setBooks((data as XhsBook[]) ?? [])
    setLoading(false)
  }

  useEffect(() => { loadBooks() }, [])

  return (
    <div className="max-w-5xl mx-auto px-8 py-10">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-xhs-primary">📚 知识库</h1>
          <p className="text-sm text-xhs-muted mt-1">上传电子资料，AI 自动生成小红书图文内容</p>
        </div>
        <button onClick={() => setShowModal(true)} className="xhs-btn-primary flex items-center gap-2">
          <span className="text-lg leading-none">＋</span>
          <span>新建书籍</span>
        </button>
      </div>

      {/* 书籍列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-24 text-xhs-muted text-sm">加载中…</div>
      ) : books.length === 0 ? (
        <EmptyState onAdd={() => setShowModal(true)} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {books.map(book => <BookCard key={book.id} book={book} />)}
        </div>
      )}

      {showModal && (
        <NewBookModal
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); loadBooks() }}
        />
      )}
    </div>
  )
}

/* ── 书籍卡片 ── */
function BookCard({ book }: { book: XhsBook }) {
  const charCount = book.raw_text?.length ?? 0
  const date = new Date(book.created_at).toLocaleDateString('zh-CN')
  return (
    <Link href={`/xhs/book/${book.id}`}>
      <div className="xhs-card cursor-pointer group h-full">
        <div className="h-1.5 w-12 rounded-full bg-xhs-accent mb-4 group-hover:w-20 transition-all duration-300" />
        <h3 className="font-semibold text-xhs-primary text-base leading-snug mb-2 line-clamp-2">
          {book.title}
        </h3>
        <span className="xhs-badge">{book.brand_name}</span>
        <div className="flex items-center gap-4 text-xs text-xhs-muted border-t border-xhs-border pt-3 mt-4">
          <span>📝 {charCount > 0 ? `${(charCount / 1000).toFixed(1)}K 字` : '暂无内容'}</span>
          <span className="ml-auto">{date}</span>
        </div>
      </div>
    </Link>
  )
}

/* ── 空状态 ── */
function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 rounded-2xl bg-orange-50 flex items-center justify-center text-3xl mb-5">📚</div>
      <h3 className="font-semibold text-xhs-primary text-lg mb-2">还没有知识库</h3>
      <p className="text-sm text-xhs-muted mb-6 max-w-xs">上传一本书或粘贴资料内容，AI 将自动分析并生成小红书图文</p>
      <button onClick={onAdd} className="xhs-btn-primary">＋ 新建第一本书</button>
    </div>
  )
}

/* ── 新建书籍弹窗 ── */
type InputMode = 'text' | 'pdf'

function NewBookModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [mode, setMode] = useState<InputMode>('text')
  const [title, setTitle] = useState('')
  const [brandName, setBrandName] = useState('大厂工程爸')
  const [rawText, setRawText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!title.trim()) { setError('请填写书名'); return }
    if (mode === 'text' && !rawText.trim()) { setError('请粘贴书籍内容'); return }
    if (mode === 'pdf' && !file) { setError('请选择 PDF 文件'); return }
    setError(''); setLoading(true)

    try {
      let res: Response
      if (mode === 'pdf' && file) {
        const form = new FormData()
        form.append('title', title)
        form.append('brand_name', brandName)
        form.append('file', file)
        res = await fetch('/api/xhs/books', { method: 'POST', body: form })
      } else {
        res = await fetch('/api/xhs/books', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, brand_name: brandName, raw_text: rawText }),
        })
      }
      if (!res.ok) {
        let msg = '创建失败'
        try { msg = (await res.json()).error ?? msg } catch { msg = `服务器错误 ${res.status}` }
        setError(msg)
        return
      }
      onCreated()
    } catch {
      setError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        {/* 弹窗头部 */}
        <div className="flex items-center justify-between p-6 pb-4 border-b border-xhs-border">
          <h2 className="text-lg font-semibold text-xhs-primary">新建书籍 / 资料</h2>
          <button onClick={onClose} className="text-xhs-muted hover:text-xhs-text text-xl w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 transition-colors">✕</button>
        </div>

        <div className="p-6 space-y-4">
          {/* 书名 */}
          <div>
            <label className="xhs-section-title block">书名 / 资料名称</label>
            <input
              className="xhs-input"
              placeholder="例：从错误开始"
              value={title}
              onChange={e => setTitle(e.target.value)}
            />
          </div>

          {/* 品牌名 */}
          <div>
            <label className="xhs-section-title block">品牌名（卡片书眉显示）</label>
            <input
              className="xhs-input"
              placeholder="大厂工程爸"
              value={brandName}
              onChange={e => setBrandName(e.target.value)}
            />
          </div>

          {/* 输入方式切换 */}
          <div>
            <label className="xhs-section-title block">内容来源</label>
            <div className="flex gap-2 mb-3">
              {(['text', 'pdf'] as InputMode[]).map(m => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 py-2 rounded-xl text-sm font-medium border transition-all ${
                    mode === m
                      ? 'border-xhs-accent bg-orange-50 text-xhs-accent'
                      : 'border-xhs-border text-xhs-muted hover:border-xhs-accent/50'
                  }`}
                >
                  {m === 'text' ? '📝 粘贴文字' : '📄 上传 PDF'}
                </button>
              ))}
            </div>

            {mode === 'text' ? (
              <textarea
                className="xhs-textarea h-40"
                placeholder="粘贴书籍原文或资料内容…"
                value={rawText}
                onChange={e => setRawText(e.target.value)}
              />
            ) : (
              <label className={`flex flex-col items-center justify-center h-32 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
                file ? 'border-xhs-accent bg-orange-50' : 'border-xhs-border hover:border-xhs-accent/50'
              }`}>
                <input type="file" accept=".pdf" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
                {file ? (
                  <>
                    <span className="text-2xl mb-1">📄</span>
                    <span className="text-sm font-medium text-xhs-accent">{file.name}</span>
                    <span className="text-xs text-xhs-muted mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  </>
                ) : (
                  <>
                    <span className="text-2xl mb-1 text-xhs-muted">⬆️</span>
                    <span className="text-sm text-xhs-muted">点击选择 PDF 文件</span>
                  </>
                )}
              </label>
            )}
          </div>

          {/* 字数提示 */}
          {mode === 'text' && rawText.length > 0 && (
            <p className="text-xs text-xhs-muted text-right">{rawText.length.toLocaleString()} 字</p>
          )}

          {/* 错误提示 */}
          {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        {/* 弹窗底部 */}
        <div className="flex gap-3 justify-end p-6 pt-0">
          <button onClick={onClose} className="xhs-btn-ghost" disabled={loading}>取消</button>
          <button onClick={submit} className="xhs-btn-primary flex items-center gap-2" disabled={loading}>
            {loading ? (
              <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />处理中…</>
            ) : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}
