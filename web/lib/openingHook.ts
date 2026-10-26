export type HookScope = 'sentences' | 'paragraph';

export function extractOpeningHook(raw: string, scope: HookScope): string {
  const text = raw.replace(/\r\n?/g, '\n').trim();
  if (!text) return '';
  const firstParagraph = text.split(/\n\s*\n|\n/).find(part => part.trim())?.trim() || text;
  const sentences = (text.match(/[^。！？!?\n]+[。！？!?]?/g) || []).map(part => part.trim()).filter(Boolean);
  if (scope === 'paragraph') return /\n/.test(text) ? firstParagraph : sentences.slice(0, 4).join('').slice(0, 180);
  return sentences.slice(0, Math.min(4, sentences.length)).join('');
}

export function markdownCell(value: string): string {
  return value.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>').trim();
}
