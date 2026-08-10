"use client";

import { Stage, StageKind, STAGES, Task } from "@/lib/types";

const COPY: Record<StageKind, { title: string; description: string }> = {
  ingest: { title: "来源素材", description: "原视频信息与公开数据已采集" },
  transcribe: { title: "逐字稿", description: "原始口播已经转成可编辑文本" },
  clean: { title: "清洗稿", description: "口语冗余和异常字符已完成整理" },
  rewrite: { title: "改写稿", description: "合规改写内容已经确认" },
  image: { title: "场景图片", description: "分镜画面与对应文案已生成" },
  book: { title: "书籍与 CTA", description: "书名、作者、封面和引导文案已确认" },
  tts: { title: "配音与字幕", description: "音色、朗读和字幕时间轴已生成" },
  render: { title: "输出规格", description: "竖版成片参数与自动质检已准备" },
};

export function PreflightPanel({ task, stages, onOpenStage }: { task: Task; stages: Stage[]; onOpenStage: (kind: StageKind) => void }) {
  const required = STAGES.filter(item => item.kind !== "render");
  const readyCount = required.filter(item => stages.find(stage => stage.kind === item.kind)?.status === "done").length;
  const total = required.length;
  const percent = Math.round((readyCount / total) * 100);
  const blockers = stages.filter(stage => stage.kind !== "render" && ["failed", "needs_review"].includes(stage.status));

  return <section className="preflight-panel anim-fade-in" aria-labelledby="preflight-title">
    <div className="preflight-hero">
      <div><p className="eyebrow">生成前确认</p><h2 id="preflight-title">成片素材是否都准备好了？</h2><p>在进入最终生成前统一核对每个环节，点击检查项可以回到对应阶段处理。</p></div>
      <div className="readiness-score" aria-label={`已完成${readyCount}项，共${total}项`}><strong>{readyCount}<span>/{total}</span></strong><small>{percent === 100 ? "全部就绪" : "准备进度"}</small></div>
    </div>
    <div className="preflight-progress"><span style={{ width: `${percent}%` }} /></div>
    {blockers.length > 0 && <div className="preflight-warning" role="status"><strong>{blockers.length} 项需要处理</strong><span>完成待确认或失败项后，再进入最终成片会更稳妥。</span></div>}
    <div className="preflight-grid">
      {STAGES.map(def => {
        const stage = stages.find(item => item.kind === def.kind);
        const status = stage?.status || "pending";
        const ready = status === "done";
        const review = status === "needs_review";
        const failed = status === "failed";
        const label = ready ? "已就绪" : review ? "待确认" : failed ? "需修复" : status === "processing" ? "生成中" : def.kind === "render" ? "待生成" : "未就绪";
        return <button className={`preflight-item is-${status}`} key={def.kind} onClick={() => onOpenStage(def.kind)}>
          <span className="preflight-check" aria-hidden="true">{ready ? "✓" : failed ? "!" : review ? "·" : String(stage?.seq ?? STAGES.findIndex(item => item.kind === def.kind) + 1)}</span>
          <span className="preflight-copy"><strong>{COPY[def.kind].title}</strong><small>{COPY[def.kind].description}</small></span>
          <span className="preflight-status">{label}</span>
        </button>;
      })}
    </div>
    <div className="preflight-footer"><div><strong>{task.title || "当前内容项目"}</strong><span>检查结果随任务进度实时更新</span></div><button className="secondary-action" onClick={() => onOpenStage("render")}>查看成片设置</button></div>
  </section>;
}
