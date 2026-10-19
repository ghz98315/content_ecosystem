"use client";

import { useEffect, useState } from 'react';
import { applyNarrationDifferences, canApplyNarrationDifference, NarrationDifference } from '@/lib/narrationEdits';

type Props = {
  differences: NarrationDifference[]; baseText: string; draft: string; canEdit: boolean;
  suggestionsReady: boolean; onApply: (text: string) => void;
  onSave: (text: string) => Promise<void>; onPreview: (start: number, end: number) => void;
};

export function NarrationDifferencesPanel({ differences, baseText, draft, canEdit,
  suggestionsReady, onApply, onSave, onPreview }: Props) {
  const [selected, setSelected] = useState<number[]>([]);
  const [replacements, setReplacements] = useState<Record<number, string>>({});
  const [undo, setUndo] = useState<{ before: string; after: string } | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    setSelected([]); setReplacements({}); setUndo(null); setError(''); setMessage('');
  }, [baseText, differences]);
  const stale = draft !== baseText;
  const editable = canEdit && suggestionsReady && !stale;
  const available = differences.flatMap((item, index) => canApplyNarrationDifference(item, baseText) ? [index] : []);
  const replacement = (index: number) => replacements[index] ?? differences[index].suggestion ?? '';
  const deletionCount = selected.filter(index => !replacement(index).trim()).length;
  const apply = async (save: boolean) => {
    setError(''); setMessage('');
    try {
      const text = applyNarrationDifferences(baseText, draft, selected.map(index => ({ difference: differences[index], replacement: replacement(index) })));
      setUndo({ before: draft, after: text }); onApply(text);
      setMessage(`已应用 ${selected.length} 项修改${save ? '，正在提交重新对齐' : '到字幕草稿，可撤销；保存后生效'}。`);
      if (save) await onSave(text);
    } catch (e) { setError(e instanceof Error ? e.message : '应用修改失败'); }
  };
  return <details className="narration-differences">
    <summary>核对朗读差异（{differences.length} 处疑似差异）</summary>
    <p>这些是文字对比片段，不是已确认的读错次数。已忽略标点、空格及数字读法差异；同音字、专名仍可能识别错误。建议按实际录音选择字幕文字。</p>
    {!suggestionsReady && <p>这是旧版核对记录。点击“生成批量修改建议”会复用识别结果重新对齐，不重新生成配音。</p>}
    {stale && <p role="status">字幕稿已修改，旧建议的位置已锁定。请保存并重新对齐后继续，避免替换错字。</p>}
    <div className="external-actions">
      <button type="button" className="secondary-action" disabled={!editable || !available.length} onClick={() => setSelected(available)}>全选可修改项（{available.length}）</button>
      <button type="button" className="secondary-action" disabled={!selected.length || !editable} onClick={() => setSelected([])}>取消全选</button>
      <button type="button" className="secondary-action" disabled={!editable || !selected.length} onClick={() => void apply(false)}>应用所选（{selected.length}）</button>
      <button type="button" className="primary-action" disabled={!editable || !selected.length} onClick={() => void apply(true)}>应用所选并保存、重新对齐</button>
      {undo && <button type="button" className="secondary-action" disabled={!canEdit || draft !== undo.after} onClick={() => { onApply(undo.before); setUndo(null); setMessage('已撤销本次草稿修改。'); }}>撤销本次修改</button>}
    </div>
    {!!deletionCount && <p className="narration-diff-warning">所选项目中有 {deletionCount} 项会删除字幕文字；请先试听，漏识别不等于漏读。</p>}
    {error && <p role="alert" className="external-error">{error}</p>}
    {message && <p role="status">{message}</p>}
    <div className="narration-diff-list">
      {differences.map((item, index) => {
        const located = canApplyNarrationDifference(item, baseText);
        return <article className="narration-diff-item" key={index}>
          <div className="narration-diff-heading"><label><input type="checkbox" checked={selected.includes(index)} disabled={!editable || !located} onChange={e => setSelected(items => e.target.checked ? [...items, index] : items.filter(i => i !== index))} />第 {index + 1} 项 · {({ replace: '文字不同', insert: '疑似增读', delete: '疑似漏读' } as Record<string, string>)[item.kind] || '待核对'}</label>
            <button type="button" className="secondary-action" disabled={item.audio_start == null || item.audio_end == null} onClick={() => onPreview(item.audio_start!, item.audio_end!)}>定位试听</button></div>
          <p>字幕原文：<strong>{(item.original ?? item.expected) || '（无）'}</strong><br />音频识别：{item.recognized || '（未识别）'}</p>
          {(item.context_before || item.context_after) && <p className="narration-diff-context">{item.context_before}<mark>{item.original || '｜插入位置｜'}</mark>{item.context_after}</p>}
          <label>修改建议（可自行编辑，留空表示删除）<input type="text" value={replacement(index)} disabled={!editable || !located} onChange={e => setReplacements(items => ({ ...items, [index]: e.target.value }))} /></label>
          <p>{item.review_hint || '请先结合实际录音核对。'}{suggestionsReady && !located && ' 该片段位置不确定，请在下方字幕稿手动修改。'}</p>
        </article>;
      })}
    </div>
  </details>;
}
