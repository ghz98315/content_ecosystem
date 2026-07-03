"use client";
import { Stage, StageKind, Task } from "@/lib/types";
import { IngestDetail }     from "./detail/IngestDetail";
import { TranscribeDetail } from "./detail/TranscribeDetail";
import { CleanDetail }      from "./detail/CleanDetail";
import { RewriteDetail }    from "./detail/RewriteDetail";
import { ImageDetail }      from "./detail/ImageDetail";
import { BookDetail }       from "./detail/BookDetail";
import { TtsDetail }        from "./detail/TtsDetail";
import { RenderDetail }     from "./detail/RenderDetail";

interface Props {
  kind: StageKind;
  stage: Stage | undefined;
  taskId: string;
  task: Task;
  onRerun: (stageId: string) => void;
  onApprove: (stageId: string, kind: string) => void;
}

export function StageDetail({ kind, stage, taskId, task, onRerun, onApprove }: Props) {
  const common = { stage, taskId, task, onRerun, onApprove };

  return (
    <div className="anim-fade-in" style={{ height: "100%", minHeight: 0 }}>
      {kind === "ingest"     && <IngestDetail     {...common} />}
      {kind === "transcribe" && <TranscribeDetail {...common} />}
      {kind === "clean"      && <CleanDetail      {...common} />}
      {kind === "rewrite"    && <RewriteDetail    {...common} />}
      {kind === "image"      && <ImageDetail      {...common} />}
      {kind === "book"       && <BookDetail       {...common} />}
      {kind === "tts"        && <TtsDetail        {...common} />}
      {kind === "render"     && <RenderDetail     {...common} />}
    </div>
  );
}
