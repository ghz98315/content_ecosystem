"use client";

interface CardData {
  type: 'cover' | 'body' | 'tail'
  title: string
  content?: string
  summary?: string
  cta?: string
  brandName: string
  pageIndex: number
  totalPages: number
}

export function XhsCard({ data, cardRef }: { data: CardData; cardRef?: (el: HTMLDivElement | null) => void }) {
  return (
    <div
      ref={cardRef}
      style={{
        width: 450,
        height: 600,
        backgroundColor: '#F8F9FA',
        fontFamily: 'PingFang SC, Microsoft YaHei, Hiragino Sans GB, sans-serif',
        position: 'relative',
        overflow: 'hidden',
        flexShrink: 0,
      }}
    >
      {data.type === 'cover' && <CoverCard data={data} />}
      {data.type === 'body'  && <BodyCard  data={data} />}
      {data.type === 'tail'  && <TailCard  data={data} />}
    </div>
  )
}

/* ── 封面页 ── */
function CoverCard({ data }: { data: CardData }) {
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '48px 40px', boxSizing: 'border-box' }}>
      {/* 装饰线 */}
      <div style={{ width: 48, height: 4, backgroundColor: '#FF6B35', borderRadius: 2, marginBottom: 32 }} />

      {/* 主标题 */}
      <h1 style={{
        fontSize: 36,
        fontWeight: 900,
        color: '#0A192F',
        textAlign: 'center',
        lineHeight: 1.4,
        margin: '0 0 16px',
      }}>
        {highlightLastTwo(data.title)}
      </h1>

      {/* 品牌署名 */}
      <div style={{
        marginTop: 40,
        fontSize: 13,
        color: '#94a3b8',
        letterSpacing: '0.1em',
        borderTop: '1px solid #e2e8f0',
        paddingTop: 16,
        width: '100%',
        textAlign: 'center',
      }}>
        {data.brandName}
      </div>

      {/* 底部装饰 */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 6, background: 'linear-gradient(90deg, #FF6B35, #0A192F)' }} />
    </div>
  )
}

/* ── 正文页 ── */
function BodyCard({ data }: { data: CardData }) {
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
      {/* 书眉 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '14px 24px',
        borderBottom: '1px solid #e2e8f0',
        fontSize: 11,
        color: '#94a3b8',
        letterSpacing: '0.05em',
        flexShrink: 0,
      }}>
        <span>{data.brandName}</span>
        <span>— {data.pageIndex} —</span>
      </div>

      {/* 正文区 */}
      <div style={{ flex: 1, display: 'flex', padding: '24px 28px 24px 20px', overflow: 'hidden' }}>
        {/* 左侧橙色竖线 */}
        <div style={{ width: 4, backgroundColor: '#FF6B35', borderRadius: 2, flexShrink: 0, marginRight: 20 }} />

        {/* 文字 */}
        <p style={{
          fontSize: 16,
          color: '#1E293B',
          lineHeight: 1.9,
          margin: 0,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 16,
          WebkitBoxOrient: 'vertical',
        }}>
          {data.content}
        </p>
      </div>

      {/* 底部页码 */}
      <div style={{
        padding: '10px 24px',
        textAlign: 'right',
        fontSize: 11,
        color: '#cbd5e1',
        borderTop: '1px solid #f1f5f9',
        flexShrink: 0,
      }}>
        {data.pageIndex} / {data.totalPages}
      </div>
    </div>
  )
}

/* ── 尾页 ── */
function TailCard({ data }: { data: CardData }) {
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', padding: '40px 36px', boxSizing: 'border-box' }}>
      {/* 顶部标签 */}
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        backgroundColor: '#fff7ed',
        color: '#FF6B35',
        borderRadius: 20,
        padding: '4px 12px',
        fontSize: 12,
        fontWeight: 600,
        marginBottom: 24,
        alignSelf: 'flex-start',
      }}>
        <span>📖</span><span>总结</span>
      </div>

      {/* 价值总结 */}
      <p style={{
        fontSize: 16,
        color: '#1E293B',
        lineHeight: 1.8,
        margin: '0 0 32px',
        flex: 1,
      }}>
        {data.summary}
      </p>

      {/* CTA 框 */}
      {data.cta && (
        <div style={{
          backgroundColor: '#F1F5F9',
          borderRadius: 16,
          padding: '16px 20px',
          fontSize: 14,
          color: '#475569',
          lineHeight: 1.7,
        }}>
          <span style={{ marginRight: 8 }}>💬</span>
          {data.cta}
        </div>
      )}

      {/* 品牌署名 */}
      <div style={{
        marginTop: 24,
        fontSize: 12,
        color: '#94a3b8',
        textAlign: 'right',
        letterSpacing: '0.08em',
      }}>
        — {data.brandName}
      </div>
    </div>
  )
}

/* ── 封面标题最后2字橙色高亮 ── */
function highlightLastTwo(title: string) {
  if (title.length <= 2) {
    return <span style={{ color: '#FF6B35' }}>{title}</span>
  }
  const body = title.slice(0, -2)
  const tail = title.slice(-2)
  return (
    <>
      {body}
      <span style={{
        color: '#FF6B35',
        borderBottom: '4px solid #FF6B35',
        paddingBottom: 2,
      }}>{tail}</span>
    </>
  )
}
