"use client";

interface Measures {
  score: number;
  phrase_overlap: number;
  sentence_reuse: number;
  sequence_similarity: number;
  longest_match: number;
  repeated_fragments: string[];
}

export interface RewriteReview {
  status: string;
  threshold: number;
  full: Measures;
  unlocked: Measures;
  locked_floor: number;
  hook_preserved: boolean;
  length_deviation: number;
  revisions_used?: number;
  max_revisions?: number;
  selected_attempt?: number;
  stop_reason?: string;
  notice?: string;
  strategy?: string[];
  comparison_summary?: string[];
  issues?: string[];
  attempts?: Array<{ attempt: number; revision: number; text: string; issues: string[]; strategy?: string[]; similarity?: {full: Measures; unlocked: Measures} }>;
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function RewriteReviewPanel({ report, source, text, evaluatedText }: {
  report: RewriteReview; source: string; text: string; evaluatedText: string;
}) {
  const edited = text !== evaluatedText;
  const manual = report.status !== 'passed';
  return <section className="rewrite-review-panel" aria-label="二创自检与原稿对照">
    <div className="rewrite-review-heading"><strong>二创自检 · {edited ? '稿件已编辑' : manual ? '请人工复核' : '本地重复检查达标'}</strong><span>自动修改 {report.revisions_used ?? 0} / {report.max_revisions ?? 3} 次</span></div>
    <p>{report.notice || '本地字面重复检测，分数不等同于文皮皮或平台检测结果。'}</p>
    {edited && <p role="status" className="rewrite-review-warning">当前文稿已编辑。下列分数对应生成稿；提交确认时会重新计算并保存最终稿指标。</p>}
    <div className="rewrite-review-metrics" aria-label={edited ? '生成稿历史检测结果' : '文稿检测结果'}>
      <div><span>全文重复指标</span><strong>{pct(report.full.score)}</strong></div>
      <div><span>除钩子外重复指标</span><strong>{pct(report.unlocked.score)}</strong></div>
      <div><span>目标</span><strong>低于 {pct(report.threshold)}</strong></div>
      <div><span>开头逐字保留</span><strong>{report.hook_preserved ? '已保留' : '需核对'}</strong></div>
    </div>
    {report.locked_floor >= report.threshold && <p className="rewrite-review-warning">锁定钩子本身带来的5字片段复用约为 {pct(report.locked_floor)}，已超过全文目标；此因素不会触发无效返工，正文仍单独检查，全文交由人工评估。</p>}
    {report.stop_reason === 'limit_reached' && <p className="rewrite-review-warning">已达到自动修改上限，已停止返工并保留稿件。请结合下方问题、重构策略和原稿对照确认。</p>}
    {report.stop_reason === 'service_error' && <p className="rewrite-review-warning">后续修改请求失败，已保留此前可用稿件，请人工确认或稍后重跑。</p>}
    {!!report.issues?.length && <ul>{report.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul>}
    {!!report.comparison_summary?.length && <details open><summary>生成时的原稿与交付稿对比摘要</summary><ul>{report.comparison_summary.map((item, i) => <li key={i}>{item}</li>)}</ul></details>}
    {!!report.strategy?.length && <details open><summary>本轮重构策略（模型提供，请结合文稿核对）</summary><ul>{report.strategy.map((strategy, i) => <li key={i}>{strategy}</li>)}</ul></details>}
    {!report.strategy?.length && <p>模型未提供具体重构策略，请结合分段对照与重复片段人工评估。</p>}
    <details><summary>查看检测细项与重复片段</summary><p>全文5字片段重合 {pct(report.full.phrase_overlap)}；整句复用 {pct(report.full.sentence_reuse)}。字符序列相似度 {pct(report.full.sequence_similarity)} 仅作参考，不用于代表语义相似度。</p><p>可改写区最长连续复用：{report.unlocked.longest_match} 字。</p>{report.unlocked.repeated_fragments.map((fragment, i) => <blockquote key={i}>{fragment}</blockquote>)}</details>
    <div className="rewrite-reading-compare"><section><h4>原稿 · 语义分段</h4><pre>{source}</pre></section><section><h4>当前改写稿</h4><pre>{text}</pre></section></div>
    <details><summary>生成与修改记录（{report.attempts?.length ?? 0} 轮）</summary>{report.attempts?.map(attempt => <details key={attempt.attempt}><summary>{attempt.revision === 0 ? '首次生成' : `第 ${attempt.revision} 次修改`}{attempt.attempt === report.selected_attempt ? ' · 当前交付稿' : ''}{attempt.similarity ? ` · 正文重复 ${pct(attempt.similarity.unlocked.score)}` : ' · 未返回有效正文'}</summary>{attempt.strategy?.map((strategy, i) => <p key={i}>{strategy}</p>)}{attempt.issues.map((issue, i) => <p key={i}>{issue}</p>)}{attempt.text && <pre>{attempt.text}</pre>}</details>)}</details>
  </section>;
}
