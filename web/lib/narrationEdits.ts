export type NarrationDifference = {
  kind: string; expected: string; recognized: string; offset?: number;
  raw_start?: number; raw_end?: number; original?: string; suggestion?: string;
  context_before?: string; context_after?: string; review_hint?: string;
  audio_start?: number; audio_end?: number;
};

export function canApplyNarrationDifference(item: NarrationDifference, base: string) {
  const { raw_start: start, raw_end: end, original } = item;
  return Number.isSafeInteger(start) && Number.isSafeInteger(end) && start! >= 0 && end! >= start!
    && end! <= base.length && typeof original === 'string' && base.slice(start, end) === original
    && typeof item.suggestion === 'string';
}

export function applyNarrationDifferences(base: string, draft: string,
  edits: Array<{ difference: NarrationDifference; replacement: string }>) {
  if (draft !== base) throw new Error('字幕稿已编辑，请先保存并重新对齐，再生成新的修改建议。');
  if (!edits.length) throw new Error('请先勾选需要修改的项目。');
  const sorted = [...edits].sort((a, b) => a.difference.raw_start! - b.difference.raw_start!);
  let end = -1, lastStart = -1;
  for (const { difference, replacement } of sorted) {
    if (!canApplyNarrationDifference(difference, base) || typeof replacement !== 'string')
      throw new Error('修改建议已失效，请重新对齐后再操作。');
    if (difference.raw_start! < end || difference.raw_start === lastStart)
      throw new Error('存在位置重叠的修改建议，请分次处理。');
    end = difference.raw_end!; lastStart = difference.raw_start!;
  }
  let result = base;
  for (const { difference, replacement } of sorted.reverse())
    result = result.slice(0, difference.raw_start) + replacement + result.slice(difference.raw_end);
  if (!result.trim()) throw new Error('修改后字幕不能为空。');
  return result;
}
