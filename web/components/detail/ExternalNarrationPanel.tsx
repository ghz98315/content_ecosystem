"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Stage } from '@/lib/types';
import { NarrationDifference } from '@/lib/narrationEdits';
import { NarrationDifferencesPanel } from './NarrationDifferencesPanel';
import { prepareMediaUpload } from '@/lib/prepareMediaUpload';

type Cue = { text: string; start: number | null; end: number | null; needs_timing_review?: boolean };
type Version = {
  id: string; state: string; subtitle_path: string | null; subtitle_text: string; original_name: string;
  review: { error?: string; recognized_text?: string; duration?: number; coverage?: number;
    audio_expired_at?: string;
    alignment_ready?: boolean; segments?: Cue[];
    differences?: NarrationDifference[]; subtitle_differences?: NarrationDifference[];
    difference_method?: string; difference_base_text?: string };
};
type Payload = { script: string; rewriteReady: boolean; audioUrl: string | null; current: Version | null;
  versions: Array<{ id: string; state: string; original_name: string; created_at: string }> };

async function authHeaders() {
  const { data } = await supabase.auth.getSession();
  if (!data.session) throw new Error('登录会话已失效');
  return { Authorization: `Bearer ${data.session.access_token}`, 'Content-Type': 'application/json' };
}

export function ExternalNarrationPanel({ stage }: { stage: Stage | undefined }) {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [draft, setDraft] = useState('');
  const [cues, setCues] = useState<Cue[]>([]);
  const [notice, setNotice] = useState('');
  const [dirtyTimes, setDirtyTimes] = useState(false);
  const [clipEnd, setClipEnd] = useState<number | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const loadedVersion = useRef('');
  const external = stage?.params.audio_source === 'external';
  const load = useCallback(async () => {
    if (!stage) return;
    const res = await fetch(`/api/narration?stageId=${encodeURIComponent(stage.id)}`, { headers: await authHeaders(), cache: 'no-store' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '读取配音失败');
    setPayload(data);
    const key = `${data.current?.id}:${data.current?.subtitle_path}`;
    if (loadedVersion.current !== key) {
      loadedVersion.current = key;
      setDraft(data.current?.subtitle_text || data.script || '');
      setCues(data.current?.review?.segments || []);
      setDirtyTimes(false);
    }
  }, [stage?.id]);
  const reviewRevision = stage?.status === 'processing' ? 'processing' : stage?.updated_at;
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load, reviewRevision]);
  useEffect(() => {
    if (stage?.status !== 'processing' && stage?.status !== 'pending') return;
    const timer = setInterval(() => void load().catch(e => setError(e.message)), 8000);
    return () => clearInterval(timer);
  }, [load, stage?.status]);

  const action = async (name: string, data: Record<string, unknown>) => {
    if (!stage) return;
    const res = await fetch('/api/narration', { method: 'PATCH', headers: await authHeaders(), body: JSON.stringify({ stageId: stage.id, action: name, data }) });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || '操作失败');
    await load();
  };
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await operation(); } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  };
  const upload = async (file: File) => {
    await perform(async () => {
      if (!stage) return;
      setUploadStatus('正在准备上传…');
      const preparedFile=await prepareMediaUpload(file,'narration',setUploadStatus);
      const res = await fetch('/api/narration', { method: 'POST', headers: await authHeaders(), body: JSON.stringify({ stageId: stage.id, name: preparedFile.name, size: preparedFile.size }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '准备上传失败');
      setUploadStatus('正在上传音频，请勿关闭页面…');
      const result = await supabase.storage.from('artifacts').uploadToSignedUrl(data.path, data.token, preparedFile, { contentType: preparedFile.name.toLowerCase().endsWith('.wav') ? 'audio/wav' : 'audio/mpeg' });
      if (result.error) throw result.error;
      await action('submit', { id: data.id });
      setUploadStatus('上传完成，等待识别与字幕对齐。');
    });
  };
  const downloadScript = () => {
    const url = URL.createObjectURL(new Blob([payload?.script || ''], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = '确认朗读稿.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const preview = (cue: Cue) => {
    if (!audio.current || cue.start == null || cue.end == null) return;
    audio.current.currentTime = cue.start; setClipEnd(cue.end); void audio.current.play().catch(() => setError('请点击播放器开始试听'));
  };
  const current = payload?.current;
  const review = current?.review;
  const suggestionsReady = review?.difference_method === 'speech_sequence_v2'
    && review?.difference_base_text === current?.subtitle_text;
  const changedText = draft.trim() !== (current?.subtitle_text || '').trim();
  const canEdit = !busy && stage?.status !== 'processing' && !!current && !review?.audio_expired_at && ['review', 'approved', 'failed'].includes(current.state);
  return <section className="external-narration-panel">
    <div className="external-heading"><div><strong>配音方式</strong><p>确认文案后，可在线下制作配音并上传；二创流程保持原样。</p></div>
      <select aria-label="配音方式" value={external ? 'external' : 'automatic'} disabled={busy || stage?.status === 'processing'} onChange={event => void perform(() => action('source', { source: event.target.value }))}>
        <option value="external">上传外部配音</option><option value="automatic">自动配音</option>
      </select>
    </div>
    {error && <p role="alert" className="external-error">{error}<button type="button" onClick={() => void perform(load)}>重试读取</button></p>}
    {external && <>
      <p>请上传无背景音乐的最终人声 WAV 或 MP3（最多 200MB、60 分钟）。大文件会在本地转成 MP3 后上传，电脑原文件不改；云端配音文件保留 48 小时，文稿和对齐记录继续保留。</p>
      <div className="external-actions">
        <button type="button" className="secondary-action" disabled={!payload?.rewriteReady || !payload.script} onClick={downloadScript}>下载确认朗读稿</button>
        <label className="secondary-action">{current ? '上传新版本' : '上传配音'}<input type="file" accept=".wav,.mp3,audio/wav,audio/mpeg" disabled={busy || !payload?.rewriteReady || stage?.status === 'processing'} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void upload(file); }} /></label>
      </div>
      {!payload?.rewriteReady && <p role="status">请先完成改写稿确认，再下载文案并上传配音。</p>}
      {uploadStatus && <p role="status">{uploadStatus}</p>}
      {busy && <progress aria-label="配音文件上传或提交中" />}
      {(current?.state === 'queued' || stage?.status === 'processing') && <p role="status">正在识别人声、自动校正识别偏差并对齐字幕，完成后自动继续。</p>}
      {review?.error && <p role="alert">处理失败：{review.error}。可以重新上传或重新对齐。</p>}
      {review?.audio_expired_at && <p role="status">配音文件已按 48 小时保留规则清理；如需重新成片，请重新上传配音。</p>}
      {payload?.audioUrl && <><p>{current?.original_name} · {review?.duration?.toFixed(1)} 秒 · {current?.state === 'approved' ? '已就绪' : '处理中'}</p>
        <audio ref={audio} controls src={payload.audioUrl} style={{ width: '100%' }} onPlay={() => { /* per-cue playback stops at its recorded end */ }} onTimeUpdate={() => {
          if (clipEnd != null && audio.current && audio.current.currentTime >= clipEnd) { audio.current.pause(); setClipEnd(null); }
        }} />
        <button type="button" className="secondary-action" onClick={() => { setClipEnd(null); void audio.current?.play(); }}>继续播放完整配音</button>
      </>}
      {review?.recognized_text && <>
        {current?.state === 'approved' && <p role="status">配音与字幕已就绪，后续自动按字幕稿继续。识别差异和时间微调可在下方按需查看，无需逐条确认。</p>}
        {current?.state === 'review' && <button type="button" className="primary-action" disabled={!canEdit || !draft.trim()} onClick={() => void perform(async () => {
          await action('realign', { id: current!.id, text: draft.trim() }); setNotice('已提交自动校正，对齐完成后将直接继续。');
        })}>旧版记录：自动校正并继续</button>}
        <details><summary>可选：查看识别差异与微调字幕</summary>
        <NarrationDifferencesPanel differences={review.subtitle_differences || review.differences || []}
          baseText={current!.subtitle_text} draft={draft} canEdit={canEdit} suggestionsReady={suggestionsReady}
          onApply={text => setDraft(text)}
          onSave={text => perform(async () => {
            await action('realign', { id: current!.id, text }); setNotice('字幕修改已保存，正在复用识别结果重新对齐。');
          })}
          onPreview={(start, end) => preview({ text: '', start, end: Math.min(end, review.duration ?? end) })} />
        {!suggestionsReady && <button type="button" className="secondary-action" disabled={!canEdit || !draft.trim()} onClick={() => void perform(async () => {
          await action('realign', { id: current!.id, text: draft.trim() }); setNotice('正在复用识别结果生成批量修改建议。');
        })}>生成批量修改建议</button>}
        <details><summary>查看完整识别文字及原确认稿差异</summary><pre>{review.recognized_text}</pre>
          {(review.differences || []).map((diff, i) => <p key={i}>确认稿：{diff.expected || '（无）'}　识别：{diff.recognized || '（未识别）'}</p>)}
        </details>
        <label>最终字幕稿<textarea value={draft} disabled={!canEdit} onChange={e => setDraft(e.target.value)} /></label>
        <p>如实际朗读有改词，请修改字幕稿并重新对齐。字幕稿只用于字幕与后续分镜，不回写二创稿。</p>
        <button type="button" className="secondary-action" disabled={!canEdit || !draft.trim()} onClick={() => void perform(async () => {
          await action('realign', { id: current!.id, text: draft.trim() }); setNotice('已提交，重新对齐会复用识别结果。');
        })}>保存字幕稿并重新对齐</button>
        <div className="external-cues" aria-label="字幕逐句校准">
          {cues.map((cue, index) => <div className="external-cue" key={index}>
            <button type="button" disabled={!payload?.audioUrl || cue.start == null || cue.end == null} onClick={() => preview(cue)}>试听 {index + 1}</button>
            <span>{cue.text}{cue.needs_timing_review && <small> · 请核对时间</small>}</span>
            {(['start', 'end'] as const).map(field => <label key={field}>{field === 'start' ? '起' : '止'}<input type="number" step="0.01" min="0" value={cue[field] ?? ''} disabled={!canEdit || changedText} onChange={event => {
              const value = event.target.value === '' ? null : Number(event.target.value);
              setCues(items => items.map((item, i) => i === index ? { ...item, [field]: value } : item)); setDirtyTimes(true);
            }} /></label>)}
          </div>)}
        </div>
        {dirtyTimes && <button type="button" className="secondary-action" disabled={!canEdit || changedText} onClick={() => void perform(() => action('realign', { id: current!.id, text: draft.trim(), cues }))}>校验并保存字幕时间</button>}
        </details>
      </>}
      {!!payload?.versions?.length && <details><summary>配音版本记录</summary>{payload.versions.map(version => <p key={version.id}>{version.original_name} · {new Date(version.created_at).toLocaleString()} · {({ uploading: '尚未提交', queued: '等待处理', review: '待核对', approved: '已确认', failed: '处理失败' } as Record<string, string>)[version.state] || version.state}
        {version.state === 'uploading' && <button type="button" disabled={busy} onClick={() => void perform(() => action('submit', { id: version.id }))}>继续提交已上传文件</button>}
      </p>)}</details>}
      {notice && <p role="status">{notice}</p>}
    </>}
  </section>;
}
