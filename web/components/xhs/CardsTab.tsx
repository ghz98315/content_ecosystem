"use client";
import { useState, useRef } from 'react'
import { XhsCard } from './XhsCard'

interface Topic { id: string; title: string }
interface CardResult { pages: string[]; summary: string; cta: string }

interface Props {
  book: { id: string; brand_name: string; raw_text: string | null }
  selectedText: string
  initialTopic?: Topic | null
}

export function CardsTab({ book, selectedText, initialTopic }: Props) {
  const [title, setTitle]       = useState(initialTopic?.title ?? '')
  const [content, setContent]   = useState('')
  const [brandName, setBrandName] = useState(book.brand_name)
  const [result, setResult]     = useState<CardResult | null>(null)
  const [loading, setLoading]   = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError]       = useState('')
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])
  const exportRefs = useRef<(HTMLDivElement | null)[]>([])

  const generate = async () => {
    if (!title.trim()) { setError('请填写主标题'); return }
    const src = content.trim() || selectedText
    if (!src) { setError('请输入原书内容或先在「内容选取」选择段落'); return }
    setError(''); setLoading(true)
    try {
      const res = await fetch('/api/xhs/cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content: src }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error ?? '生成失败'); return }
      setResult(data)
      cardRefs.current = []
    } catch {
      setError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  const exportZip = async () => {
    if (!result || !title) return
    setExporting(true)
    try {
      const { toPng } = await import('html-to-image')
      const JSZip = (await import('jszip')).default
      const { saveAs } = await import('file-saver')

      const zip = new JSZip()
      // 抓隐藏的原始尺寸节点（不受 scale 影响）
      const cards = exportRefs.current.filter(Boolean) as HTMLDivElement[]

      for (let i = 0; i < cards.length; i++) {
        const dataUrl = await toPng(cards[i], { pixelRatio: 2, skipFonts: false })
        const base64 = dataUrl.split(',')[1]
        zip.file(`${title}-${i + 1}.png`, base64, { base64: true })
      }

      const blob = await zip.generateAsync({ type: 'blob' })
      saveAs(blob, `${title}.zip`)
    } catch (e) {
      setError('导出失败，请重试')
      console.error(e)
    } finally {
      setExporting(false)
    }
  }

  // 构建卡片数据数组
  const buildCards = () => {
    if (!result) return []
    const total = result.pages.length + 2 // 封面 + 正文 + 尾页
    return [
      { type: 'cover' as const, title, brandName, pageIndex: 0, totalPages: total },
      ...result.pages.map((p, i) => ({
        type: 'body' as const,
        title,
        content: p,
        brandName,
        pageIndex: i + 1,
        totalPages: total,
      })),
      { type: 'tail' as const, title, summary: result.summary, cta: result.cta, brandName, pageIndex: total, totalPages: total },
    ]
  }

  const cards = buildCards()

  return (
    <div className="flex gap-6 p-8 max-w-7xl mx-auto">
      {/* 左侧：输入区 */}
      <div className="w-72 flex-shrink-0 space-y-4">
        <div className="bg-white rounded-2xl border border-xhs-border p-5 space-y-4">
          <h3 className="font-semibold text-xhs-primary">卡片参数</h3>

          <div>
            <label className="xhs-section-title block">主标题</label>
            <input className="xhs-input" placeholder="例：大厂爸爸的除错笔记" value={title} onChange={e => setTitle(e.target.value)} />
          </div>

          <div>
            <label className="xhs-section-title block">品牌名</label>
            <input className="xhs-input" placeholder="大厂工程爸" value={brandName} onChange={e => setBrandName(e.target.value)} />
          </div>

          <div>
            <label className="xhs-section-title block">原书内容</label>
            <textarea
              className="xhs-textarea h-32"
              placeholder="粘贴原书段落，或留空使用已选内容…"
              value={content}
              onChange={e => setContent(e.target.value)}
            />
            {selectedText && !content && (
              <button onClick={() => setContent(selectedText.slice(0, 1500))} className="text-xs text-xhs-accent hover:underline mt-1">
                导入已选内容（前 1500 字）
              </button>
            )}
          </div>

          <button onClick={generate} disabled={loading} className="xhs-btn-primary w-full flex items-center justify-center gap-2">
            {loading
              ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />生成中…</>
              : '🎨 AI 智能切分'}
          </button>

          {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        {/* 导出按钮 */}
        {cards.length > 0 && (
          <button onClick={exportZip} disabled={exporting} className="xhs-btn-primary w-full flex items-center justify-center gap-2">
            {exporting
              ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />导出中…</>
              : `⬇️ 导出整套图文 ZIP（${cards.length} 张）`}
          </button>
        )}
      </div>

      {/* 右侧：卡片预览区 */}
      <div className="flex-1 min-w-0">
        {cards.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center bg-white rounded-2xl border border-xhs-border">
            <div className="text-4xl mb-4">🎨</div>
            <p className="text-sm text-xhs-muted">填写参数后点击「AI 智能切分」生成卡片预览</p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-xhs-muted">共 {cards.length} 张卡片（导出尺寸 900×1200px）</p>
            </div>
            <div className="flex flex-wrap gap-4">
              {cards.map((card, i) => (
                <div key={i} style={{ transform: 'scale(0.6)', transformOrigin: 'top left', width: 450, height: 600, marginBottom: -240, marginRight: -180 }}>
                  <XhsCard
                    data={card}
                    cardRef={(el: HTMLDivElement | null) => { cardRefs.current[i] = el }}
                  />
                </div>
              ))}
            </div>

            {/* 隐藏的原始尺寸节点，供 html-to-image 导出用 */}
            <div style={{ position: 'absolute', left: -9999, top: 0, pointerEvents: 'none' }}>
              {cards.map((card, i) => (
                <XhsCard
                  key={`export-${i}`}
                  data={card}
                  cardRef={(el: HTMLDivElement | null) => { exportRefs.current[i] = el }}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
