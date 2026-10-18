"use client";

import { useEffect, useState } from 'react';
import { authenticatedFetch } from '@/lib/authenticatedFetch';
import { characterCount, PublicationCopy, PUBLICATION_FIELDS, publicationText, validatePublication } from '@/lib/publication';

type RecordEntry = { id: string; created_at: string; meta: { copy: PublicationCopy; source_hash: string } };
type Loaded = { record: RecordEntry | null; ready: boolean; sourceHash: string | null; stale: boolean; sourceTitle: string; sourceTags: string[] };

export function PublicationPanel({ taskId }: { taskId: string }) {
  const [data, setData] = useState<Loaded | null>(null);
  const [copy, setCopy] = useState<PublicationCopy | null>(null);
  const [draftHash, setDraftHash] = useState('');
  const [busy, setBusy] = useState('load');
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [tagsInput, setTagsInput] = useState('');
  const cacheKey = `publication-draft:${taskId}`;

  useEffect(() => {
    let active = true;
    setBusy('load'); setError('');
    (async () => {
      const response = await authenticatedFetch(`/api/publication?taskId=${taskId}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '发布文案读取失败');
      if (!active) return;
      setData(result); setCopy(result.record?.meta.copy || null); setTagsInput((result.record?.meta.copy.tags || []).map((tag: string) => `#${tag}`).join(' ')); setDraftHash(result.record?.meta.source_hash || result.sourceHash || ''); setDirty(false);
      try {
        const cached = JSON.parse(sessionStorage.getItem(cacheKey) || 'null');
        if (cached && (cached.baseId || null) === (result.record?.id || null)) {
          if (cached.copy && PUBLICATION_FIELDS.every(field => typeof cached.copy[field.key] === 'string') && Array.isArray(cached.copy.cover_options) && Array.isArray(cached.copy.publish_titles) && Array.isArray(cached.copy.tags) && Array.isArray(cached.copy.replies) && typeof cached.sourceHash === 'string') {
            setCopy(cached.copy); setTagsInput(cached.copy.tags.map((tag: string) => `#${tag}`).join(' ')); setDraftHash(cached.sourceHash); setDirty(true); setMessage('已恢复本标签页的未保存草稿');
          }
        }
      } catch { /* An incomplete local draft never replaces the saved version. */ }
    })().catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setBusy(''); });
    return () => { active = false; };
  }, [taskId, reload, cacheKey]);

  useEffect(() => {
    if (!dirty || !copy || !data) return;
    try { sessionStorage.setItem(cacheKey, JSON.stringify({ copy, sourceHash: draftHash, baseId: data.record?.id || null })); }
    catch { /* Saving to the server remains available when local storage is full. */ }
  }, [copy, dirty, draftHash, data, cacheKey]);

  const edit = (next: PublicationCopy) => { setCopy(next); setDirty(true); setMessage('有未保存修改'); setError(''); };
  const stale = Boolean(copy && data && draftHash !== data.sourceHash);

  async function generate() {
    if (dirty && !window.confirm('重新生成会替换当前未保存草稿，是否继续？')) return;
    setBusy('generate'); setError(''); setMessage('正在根据最终确认稿生成…');
    try {
      const response = await authenticatedFetch('/api/publication', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ taskId, action: 'generate', sourceHash: data?.sourceHash }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '生成失败');
      setCopy(result.copy); setTagsInput(result.copy.tags.map((tag: string) => `#${tag}`).join(' ')); setDraftHash(result.sourceHash); setDirty(true); setMessage('已生成草稿，检查后点击保存发布文案');
    } catch (err) { setError(err instanceof Error ? err.message : '生成失败'); setMessage(''); }
    finally { setBusy(''); }
  }

  async function save() {
    if (!copy) return;
    setBusy('save'); setError('');
    try {
      const valid = validatePublication(copy);
      const response = await authenticatedFetch('/api/publication', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ taskId, action: 'save', copy: valid, sourceHash: draftHash, baseId: data?.record?.id || null }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '保存失败');
      setData(previous => previous ? { ...previous, record: result.record, stale: false } : previous); setCopy(valid); setDirty(false);
      try { sessionStorage.removeItem(cacheKey); } catch { /* Optional local cache. */ }
      setMessage('已保存发布文案；历史版本保留，图片和视频清理不影响文案记录');
    } catch (err) { setError(err instanceof Error ? err.message : '保存失败'); }
    finally { setBusy(''); }
  }

  async function clipboard(value: string) {
    try { await navigator.clipboard.writeText(value); setMessage(dirty ? '已复制当前草稿，记得保存修改' : '已复制'); }
    catch { setError('复制失败，请手动选择文字复制'); }
  }

  return <section className="publication-editor" aria-labelledby="publication-editor-title" aria-busy={Boolean(busy)}>
    <div className="render-panel-heading"><div><strong id="publication-editor-title">发布文案包</strong><span>根据最终确认稿设计，可编辑并逐项复制。发布封面文案独立保存；视频画面文字仍在原设置中调整。</span></div>
      <button className="secondary-action" disabled={Boolean(busy) || !data?.ready} onClick={generate}>{busy === 'generate' ? '生成中…' : copy ? '重新生成' : '根据文案生成'}</button></div>
    {busy === 'load' && <p role="status">正在读取发布文案…</p>}
    {data && !data.ready && <p className="publication-warning">请先确认改写文案，完成后可生成发布内容。</p>}
    {stale && <p className="publication-warning" role="status">确认稿已经变化，当前为旧稿的发布文案，请重新生成后保存。</p>}
    {data?.sourceTitle && <details className="publication-source"><summary>参考原标题与标签</summary><p>{data.sourceTitle}</p><small>{data.sourceTags.map(tag => `#${tag}`).join(' ')}</small></details>}
    {copy && <>
      <fieldset className="publication-choices"><legend>封面主副标题 · 三选一</legend><div className="cover-choice-grid">{copy.cover_options.map((option, index) => <button type="button" key={index} disabled={Boolean(busy)} aria-pressed={copy.cover_title === option.title && copy.cover_subtitle === option.subtitle} onClick={() => edit({ ...copy, cover_title: option.title, cover_subtitle: option.subtitle })}><small>方案 {String(index + 1).padStart(2, '0')}</small><strong>{option.title}</strong><span>{option.subtitle}</span></button>)}</div></fieldset>
      <fieldset className="publication-choices"><legend>发布标题 · 三选一</legend><div className="publish-choice-list">{copy.publish_titles.map((title, index) => <button type="button" key={index} disabled={Boolean(busy)} aria-pressed={copy.publish_title === title} onClick={() => edit({ ...copy, publish_title: title })}><small>{String(index + 1).padStart(2, '0')}</small><span>{title}</span></button>)}</div></fieldset>
      <div className="publication-fields">{PUBLICATION_FIELDS.map(field => <label key={field.key} className={field.key.includes('comment') || field.key === 'description' ? 'publication-wide' : ''}>
        <span>{field.label}<small>{characterCount(copy[field.key])}/{field.max}字</small></span>
        <textarea aria-label={field.label} rows={field.rows} value={copy[field.key]} disabled={Boolean(busy)} onChange={event => edit({ ...copy, [field.key]: event.target.value })} />
        <button type="button" onClick={() => void clipboard(copy[field.key])}>复制{field.label}</button>
      </label>)}
      <label className="publication-wide"><span>话题标签<small>最多8个，以空格或 # 分隔</small></span><input aria-label="话题标签" disabled={Boolean(busy)} value={tagsInput} onChange={event => { setTagsInput(event.target.value); edit({ ...copy, tags: event.target.value.split(/[\s#]+/).filter(Boolean) }); }} /><button onClick={() => void clipboard(copy.tags.map(tag => `#${tag}`).join(' '))}>复制话题标签</button></label>
      </div>
      <div className="publication-replies"><div className="section-heading"><strong>回复建议</strong><small>按实际评论选用，每条50字以内，最多5条</small></div>
        {copy.replies.map((reply, index) => <label key={index}><span>{index + 1}</span><textarea aria-label={`回复建议${index + 1}`} rows={2} disabled={Boolean(busy)} value={reply} onChange={event => edit({ ...copy, replies: copy.replies.map((item, i) => i === index ? event.target.value : item) })} /><small>{characterCount(reply)}/50字</small><button onClick={() => void clipboard(reply)}>复制</button><button disabled={Boolean(busy)} aria-label={`移除回复建议${index + 1}`} onClick={() => edit({ ...copy, replies: copy.replies.filter((_, i) => i !== index) })}>移除</button></label>)}
        {copy.replies.length < 5 && <button className="secondary-action" disabled={Boolean(busy)} onClick={() => edit({ ...copy, replies: [...copy.replies, ''] })}>添加回复建议</button>}
      </div>
      <div className="publication-toolbar"><button className="primary-action" onClick={save} disabled={Boolean(busy) || !dirty || stale || !data?.ready}>{busy === 'save' ? '保存中…' : '保存发布文案'}</button><button className="secondary-action" onClick={() => void clipboard(publicationText(copy))}>复制全部</button><small>{dirty ? '未保存草稿' : data?.record ? `已保存于 ${new Date(data.record.created_at).toLocaleString('zh-CN', { hour12: false })}` : ''}</small></div>
    </>}
    {message && <p role="status" className="publication-copy-notice">{message}</p>}
    {error && <div role="alert" className="notice notice-error">{error}{!data && <button className="secondary-action" onClick={() => setReload(value => value + 1)}>重试读取</button>}</div>}
  </section>;
}
