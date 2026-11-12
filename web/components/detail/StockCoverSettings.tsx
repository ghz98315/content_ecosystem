'use client';

import { useEffect, useState } from 'react';
import { authenticatedFetch } from '@/lib/authenticatedFetch';
import { supabase } from '@/lib/supabase';

type GeneratedCover = { path: string; sourceUrl?: string; referenceStatus?: string; prompt?: string };

export function StockCoverSettings({ taskId, rerender = false, generatedCover, imageProcessing = false }: {
  taskId: string;
  rerender?: boolean;
  generatedCover?: GeneratedCover;
  imageProcessing?: boolean;
}) {
  const [mode, setMode] = useState<'stock' | 'history' | null>(null);
  const [path, setPath] = useState('');
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setMode(null); setPath('');
    void Promise.all([
      supabase.from('stages').select('params').eq('task_id', taskId).eq('kind', 'render').single(),
      supabase.from('tasks').select('content_category,narration_mode').eq('id', taskId).single(),
    ]).then(([{ data }, { data: task }]) => {
        if (!active || !data) return;
        const history = task?.narration_mode !== 'dual_dialogue'
          && (data.params?.content_line || task?.content_category) === 'social_science';
        setMode(data.params?.visual_mode === 'stock_video' ? 'stock' : history ? 'history' : null);
        setPath(String(data.params?.video_cover_path || ''));
      });
    return () => { active = false; };
  }, [taskId]);

  const previewPath = path || (mode === 'history' ? generatedCover?.path : '');
  useEffect(() => {
    let active = true;
    setPreview('');
    if (previewPath) void authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(previewPath)}`)
      .then(response => {
        if (!response.ok) throw new Error('封面预览读取失败');
        return response.json();
      }).then(data => { if (active) setPreview(data.signedUrl || ''); })
      .catch(() => { if (active) setError('封面预览读取失败'); });
    return () => { active = false; };
  }, [previewPath]);

  async function save(file?: File, reset = false, run = false) {
    setBusy(true); setError(''); setMessage('');
    try {
      const { data: stage, error: readError } = await supabase.from('stages').select('id,status,updated_at,params')
        .eq('task_id', taskId).eq('kind', 'render').single();
      if (readError || !stage) throw new Error('成片设置读取失败');
      if (stage.status === 'processing') throw new Error('视频正在合成，请稍后再修改');
      if (mode === 'history' && (file || reset)) {
        const { data: image, error: imageError } = await supabase.from('stages').select('status')
          .eq('task_id', taskId).eq('kind', 'image').single();
        if (imageError || !image) throw new Error('生图状态读取失败');
        if (image.status === 'processing') throw new Error('本批图片正在生成，请稍后再修改封面');
      }
      if (file || reset) {
        let next: string | null = null;
        if (file) {
          if (!/\.(png|jpe?g|webp)$/i.test(file.name) || file.size > 5 * 1024 * 1024 || !file.size) {
            throw new Error('请选择 5 MB 以内的 PNG、JPG 或 WebP 封面');
          }
          const picture = await createImageBitmap(file);
          picture.close();
          const response = await authenticatedFetch('/api/video-cover', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({taskId, name:file.name, size:file.size}),
          });
          const upload = await response.json();
          if (!response.ok) throw new Error(upload.error || '准备封面上传失败');
          const { error: uploadError } = await supabase.storage.from('artifacts')
            .uploadToSignedUrl(upload.path, upload.token, file, {contentType:file.type || 'application/octet-stream'});
          if (uploadError) throw uploadError;
          next = upload.path;
        }
        const { data, error: saveError } = await supabase.from('stages').update({ params: { ...stage.params, video_cover_path: next } })
          .eq('id', stage.id).eq('updated_at', stage.updated_at).neq('status', 'processing').select('id');
        if (saveError || !data?.length) throw new Error('任务设置已变化，请刷新后重试');
        setPath(next || '');
        setMessage(next ? '任务封面已保存，下次成片时使用。' : mode === 'history'
          ? '已恢复自动封面。已有专用封面可直接复用，也可重跑生图生成新的首格封面。'
          : '已恢复按书名查找本地预设或从素材中选帧。');
      }
      if (run) {
        const { error: rerunError } = await supabase.rpc('rerun_stage', {p_stage_id:stage.id});
        if (rerunError) throw new Error(rerunError.message);
        setMessage('已排队重新成片，沿用已选片段、配音和字幕。');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '封面设置失败');
    } finally { setBusy(false); }
  }

  if (!mode) return null;
  const history = mode === 'history';
  const canEdit = !busy && !(history && imageProcessing);
  return <section className="book-info-panel" aria-label="成片封面" style={{padding:16,margin:'16px 0'}}>
    <h3>成片封面（可选）</h3>
    <p>{history ? '生图前可上传封面。采用自动封面时，系统根据整篇文案设计首批九宫格左上角。'
      : '可上传本任务封面。未上传时按书名查找「91_成片预设封面」，没有匹配项时从已选素材中取帧。'}</p>
    <label>上传成片封面 <input type="file" accept=".png,.jpg,.jpeg,.webp" disabled={!canEdit} onChange={event => {
      const file = event.currentTarget.files?.[0]; event.currentTarget.value = '';
      if (file) void save(file);
    }} /></label>
    {path && <p>上传封面按顶部对齐裁为 4:3，成片时做高清处理。</p>}
    {preview && <img src={preview} alt="任务封面预览" style={path
      ? {display:'block',width:'100%',maxWidth:240,aspectRatio:'4 / 3',objectFit:'cover',objectPosition:'center top'}
      : {display:'block',maxWidth:240,maxHeight:200,objectFit:'contain'}} />}
    {history && !path && generatedCover?.referenceStatus !== 'safe_fallback' && generatedCover?.sourceUrl && /^https:\/\/commons\.wikimedia\.org\//.test(generatedCover.sourceUrl) &&
      <p><a href={generatedCover.sourceUrl} target="_blank" rel="noreferrer">查看肖像参考来源</a>{generatedCover.referenceStatus === 'text_only' ? '（本通道按时代地域示意）' : ''}</p>}
    {history && !path && generatedCover?.referenceStatus === 'illustrative' && <p>封面为时代与地域相符的示意形象。</p>}
    {history && !path && generatedCover?.referenceStatus === 'safe_fallback' && <p>封面采用与主题相符的场景与器物。</p>}
    {history && !path && generatedCover?.prompt && <details className="image-prompt-full">
      <summary>封面提示词</summary><pre>{generatedCover.prompt}</pre>
    </details>}
    <div className="external-actions">
      {path && <button type="button" disabled={!canEdit} onClick={() => void save(undefined,true)}>恢复自动封面</button>}
      {rerender && <button type="button" disabled={busy} onClick={() => void save(undefined,false,true)}>应用封面并重新成片</button>}
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
