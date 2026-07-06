"use client";
export const dynamic = "force-dynamic";

import { useEffect, useState, useCallback } from 'react'
import { supabase } from '@/lib/supabase'
import { useParams } from 'next/navigation'
import { TopicsTab } from '@/components/xhs/TopicsTab'
import { CopyTab } from '@/components/xhs/CopyTab'
import { CardsTab } from '@/components/xhs/CardsTab'

type Tab = 'topics' | 'copy' | 'cards' | 'settings'

interface XhsBook {
  id: string
  title: string
  brand_name: string
  raw_text: string | null
  file_url: string | null
  created_at: string
}

interface Topic {
  id: string
  title: string
  pain_point: string
  logic: string
}

function splitParagraphs(text: string): string[] {
  return text.split(/\n{2,}/).map(p => p.trim()).filter(p => p.length > 20)
}

export default function XhsBookPage() {
  const { id } = useParams<{ id: string }>()
  const [book, setBook] = useState<XhsBook | null>(null)
  const [tab, setTab] = useState<Tab>('topics')
  const [loading, setLoading] = useState(true)
  const [selectedParas, setSelectedParas] = useState<Set<number>>(new Set())
  const [copyTopic, setCopyTopic] = useState<Topic | null>(null)
  const [cardTopic, setCardTopic] = useState<Topic | null>(null)

  const loadBook = useCallback(async () => {
    const { data } = await supabase.from('xhs_books').select('*').eq('id', id).single()
    if (data) {
      setBook(data as XhsBook)
      const paras = splitParagraphs((data as XhsBook).raw_text ?? '')
      setSelectedParas(new Set(paras.map((_, i) => i)))
    }
    setLoading(false)
  }, [id])

  useEffect(() => { loadBook() }, [loadBook])

  if (loading) return <div className="flex items-center justify-center py-24 text-xhs-muted text-sm">加载中…</div>
  if (!book) return <div className="flex items-center justify-center py-24 text-xhs-muted text-sm">书籍不存在</div>

  const paras = splitParagraphs(book.raw_text ?? '')
  const selectedText = paras.filter((_, i) => selectedParas.has(i)).join('\n\n')

  const goToCopy = (topic: Topic) => { setCopyTopic(topic); setTab('copy') }
  const goToCards = (topic: Topic) => { setCardTopic(topic); setTab('cards') }

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: 'topics',   label: '主题矩阵',   icon: '📌' },
    { key: 'copy',     label: '文案生成室', icon: '✍️'  },
    { key: 'cards',    label: '卡片工厂',   icon: '🎨' },
    { key: 'settings', label: '内容选取',   icon: '📋' },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* 顶部书名栏 */}
      <div className="bg-white border-b border-xhs-border px-8 py-4 flex items-center gap-3 flex-wrap">
        <a href="/xhs" className="text-xhs-muted hover:text-xhs-accent text-sm transition-colors">← 知识库</a>
        <span className="text-xhs-muted">/</span>
        <h1 className="font-semibold text-xhs-primary text-base">{book.title}</h1>
        <span className="xhs-badge">{book.brand_name}</span>
        {paras.length > 0 && (
          <span className="ml-auto text-xs text-xhs-muted">
            已选 {selectedParas.size}/{paras.length} 段 · {selectedText.length.toLocaleString()} 字
          </span>
        )}
      </div>

      {/* Tab 导航 */}
      <div className="bg-white border-b border-xhs-border px-8">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors duration-150 ${
                tab === t.key
                  ? 'border-xhs-accent text-xhs-accent'
                  : 'border-transparent text-xhs-muted hover:text-xhs-text'
              }`}
            >
              <span>{t.icon}</span><span>{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab 内容：用 display 隐藏而非卸载，保留各 tab 的 state */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        <div style={{ display: tab === 'topics' ? undefined : 'none' }}>
          <TopicsTab
            book={book}
            selectedText={selectedText}
            onGoToCopy={goToCopy}
            onGoToCards={goToCards}
          />
        </div>
        <div style={{ display: tab === 'copy' ? undefined : 'none' }}>
          <CopyTab
            book={book}
            selectedText={selectedText}
            initialTopic={copyTopic}
            onGoToCards={(title: string) => { setCardTopic({ id: '', title, pain_point: '', logic: '' }); setTab('cards') }}
          />
        </div>
        <div style={{ display: tab === 'cards' ? undefined : 'none' }}>
          <CardsTab
            book={book}
            selectedText={selectedText}
            initialTopic={cardTopic}
          />
        </div>
        <div style={{ display: tab === 'settings' ? undefined : 'none' }}>
          <SettingsTab
            book={book}
            paras={paras}
            selectedParas={selectedParas}
            onSelectionChange={setSelectedParas}
            onBookUpdate={setBook}
          />
        </div>
      </div>
    </div>
  )
}

/* ── 内容选取 Tab ── */
function SettingsTab({
  book, paras, selectedParas, onSelectionChange, onBookUpdate,
}: {
  book: XhsBook
  paras: string[]
  selectedParas: Set<number>
  onSelectionChange: (s: Set<number>) => void
  onBookUpdate: (b: XhsBook) => void
}) {
  const [brandName, setBrandName] = useState(book.brand_name)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const toggleAll = () => {
    onSelectionChange(
      selectedParas.size === paras.length ? new Set() : new Set(paras.map((_, i) => i))
    )
  }

  const toggle = (i: number) => {
    const next = new Set(selectedParas)
    next.has(i) ? next.delete(i) : next.add(i)
    onSelectionChange(next)
  }

  const saveBrand = async () => {
    setSaving(true)
    const res = await fetch(`/api/xhs/books/${book.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brand_name: brandName }),
    })
    if (res.ok) {
      onBookUpdate(await res.json())
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    }
    setSaving(false)
  }

  return (
    <div className="max-w-3xl mx-auto px-8 py-8 space-y-6">
      {/* 品牌名 */}
      <div className="bg-white rounded-2xl border border-xhs-border p-6">
        <h3 className="font-semibold text-xhs-primary mb-4">卡片品牌名</h3>
        <div className="flex gap-3">
          <input className="xhs-input flex-1" value={brandName}
            onChange={e => setBrandName(e.target.value)} placeholder="大厂工程爸" />
          <button onClick={saveBrand} disabled={saving} className="xhs-btn-primary min-w-16">
            {saved ? '✓ 已保存' : saving ? '保存中…' : '保存'}
          </button>
        </div>
        <p className="text-xs text-xhs-muted mt-2">显示在卡片左上角书眉位置</p>
      </div>

      {/* 段落选取 */}
      <div className="bg-white rounded-2xl border border-xhs-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-xhs-primary">内容段落选取</h3>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-xhs-muted">已选 {selectedParas.size}/{paras.length} 段</span>
            <button onClick={toggleAll} className="xhs-btn-ghost py-1 px-3 text-xs">
              {selectedParas.size === paras.length ? '取消全选' : '全选'}
            </button>
          </div>
        </div>

        {paras.length === 0 ? (
          <p className="text-sm text-xhs-muted text-center py-8">暂无内容，请先录入书籍文字</p>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {paras.map((para, i) => (
              <label key={i} className={`flex gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                selectedParas.has(i)
                  ? 'border-xhs-accent/40 bg-orange-50/50'
                  : 'border-xhs-border hover:border-xhs-accent/30'
              }`}>
                <input type="checkbox" checked={selectedParas.has(i)} onChange={() => toggle(i)}
                  className="mt-0.5 w-4 h-4 accent-[#FF6B35] flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-medium text-xhs-muted">第 {i+1} 段</span>
                    <span className="text-xs text-xhs-muted">{para.length} 字</span>
                  </div>
                  <p className="text-sm text-xhs-text leading-relaxed line-clamp-3">{para}</p>
                </div>
              </label>
            ))}
          </div>
        )}

        <div className="mt-4 pt-4 border-t border-xhs-border text-xs text-xhs-muted flex gap-2">
          <span>💡</span>
          <span>已选内容将用于主题矩阵生成和卡片制作，不相关章节可取消勾选</span>
        </div>
      </div>
    </div>
  )
}
