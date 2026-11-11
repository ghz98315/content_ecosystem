'use client';

import { useEffect, useState } from 'react';
import { authenticatedFetch } from '@/lib/authenticatedFetch';
import { supabase } from '@/lib/supabase';

export function StockCoverSettings({ taskId, rerender = false }: { taskId: string; rerender?: boolean }) {
  const [enabled, setEnabled] = useState(false);
  const [path, setPath] = useState('');
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setEnabled(false); setPath('');
    void supabase.from('stages').select('params').eq('task_id', taskId).eq('kind', 'render').single()
      .then(({ data }) => {
        if (!active || !data) return;
        setEnabled(data.params?.visual_mode === 'stock_video');
        setPath(String(data.params?.video_cover_path || ''));
      });
    return () => { active = false; };
  }, [taskId]);

  useEffect(() => {
    let active = true;
    setPreview('');
    if (path) void authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`)
      .then(response => response.json()).then(data => { if (active) setPreview(data.signedUrl || ''); })
      .catch(() => { if (active) setError('封面预览读取失败'); });
    return () => { active = false; };
  }, [path]);

  async function save(file?: File, reset = false, run = false) {
    setBusy(true); setError(''); setMessage('');
    try {
      const { data: stage, error: readError } = await supabase.from('stages').select('id,status,updated_at,params')
        .eq('task_id', taskId).eq('kind', 'render').single();
      if (readError || !stage) throw new Error('成片设置读取失败');
      if (stage.status === 'processing') throw new Error('视频正在合成，请稍后再修改');
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
        setMessage(next ? '任务封面已保存，下次成片时使用。' : '已恢复按书名查找本地预设或从素材中选帧。');
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

  if (!enabled) return null;
  return <section className="book-info-panel" aria-label="成片封面" style={{padding:16,margin:'16px 0'}}>
    <h3>成片封面（可选）</h3>
    <p>可上传本任务封面。未上传时按书名查找「91_成片预设封面」，没有匹配项时从已选素材中取帧。</p>
    <label>上传成片封面 <input type="file" accept=".png,.jpg,.jpeg,.webp" disabled={busy} onChange={event => {
      const file = event.currentTarget.files?.[0]; event.currentTarget.value = '';
      if (file) void save(file);
    }} /></label>
    {preview && <img src={preview} alt="任务封面预览" style={{display:'block',maxWidth:240,maxHeight:200,objectFit:'contain'}} />}
    <div className="external-actions">
      {path && <button type="button" disabled={busy} onClick={() => void save(undefined,true)}>恢复自动封面</button>}
      {rerender && <button type="button" disabled={busy} onClick={() => void save(undefined,false,true)}>应用封面并重新成片</button>}
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
