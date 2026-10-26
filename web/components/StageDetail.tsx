"use client";
import { Stage, StageKind, Task } from "@/lib/types";
import { IngestDetail }     from "./detail/IngestDetail";
import { RewriteDetail }    from "./detail/RewriteDetail";
import { ImageDetail }      from "./detail/ImageDetail";
import { StockVideoDetail } from './detail/StockVideoDetail';
import { BookDetail }       from "./detail/BookDetail";
import { TtsDetail }        from "./detail/TtsDetail";
import { RenderDetail }     from "./detail/RenderDetail";
import { TranscriptCleanWorkbench } from "./detail/TranscriptCleanWorkbench";

interface Props {
  kind: StageKind;
  stage: Stage | undefined;
  taskId: string;
  task: Task;
  stages: Stage[];
  onRerun: (stageId: string) => void;
  onApprove: (stageId: string, kind: string) => void;
}

export function StageDetail({ kind, stage, stages, taskId, task, onRerun, onApprove }: Props) {
  const common = { stage, taskId, task, onRerun, onApprove };

  if (stage?.params.input_mode === 'ready_script' && ['ingest', 'transcribe', 'clean'].includes(kind)) {
    return <div className="state-panel"><strong>已直接导入确认成稿</strong><span>此任务跳过采集、逐字稿和清洗，后续使用导入的完整文案。</span></div>;
  }

  return (
    <div className="anim-fade-in" style={{ height: "100%", minHeight: 0 }}>
      {kind === "ingest"     && <IngestDetail     {...common} />}
      {(kind === "transcribe" || kind === "clean") && <TranscriptCleanWorkbench stages={stages} onRerun={onRerun} />}
      {kind === "rewrite"    && <RewriteDetail    {...common} />}
      {kind === "image"      && (stage?.params.visual_mode === 'stock_video' ? <StockVideoDetail {...common}/> : <ImageDetail {...common}/>)}
      {kind === "book"       && <BookDetail       {...common} />}
      {kind === "tts"        && <TtsDetail        {...common} />}
      {kind === "render"     && <RenderDetail     {...common} />}
    </div>
  );
}
