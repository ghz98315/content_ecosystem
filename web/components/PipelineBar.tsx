"use client";
import { Stage, StageKind, STAGES } from "@/lib/types";

interface Props {
  stages: Stage[];
  selected: StageKind;
  onSelect: (kind: StageKind) => void;
}

const STATUS_ICON: Record<string, string> = {
  pending:      "○",
  processing:   "↻",
  done:         "✓",
  failed:       "✗",
  needs_review: "⏸",
  cancelled:    "—",
};

export function PipelineBar({ stages, selected, onSelect }: Props) {
  return (
    <div className="pipeline-bar">
      {STAGES.map((def, i) => {
        const st = stages.find(s => s.kind === def.kind);
        const status = st?.status ?? "pending";
        const isSelected = selected === def.kind;
        const isProcessing = status === "processing";
        const isReview = status === "needs_review";

        const dotColor =
          status === "pending"      ? "var(--status-pending)"    :
          status === "processing"   ? "var(--status-processing)" :
          status === "done"         ? "var(--status-done)"       :
          status === "failed"       ? "var(--status-failed)"     :
          status === "needs_review" ? "var(--status-review)"     :
          "var(--status-cancelled)";

        return (
          <button
            key={def.kind}
            onClick={() => onSelect(def.kind)}
            className={`pipeline-step ${isSelected ? "" : "hoverable"}`}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "0 14px", border: "none", background: "none",
              cursor: "pointer", flexShrink: 0, position: "relative",
              color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: 13,
              transition: "background 0.12s ease, color 0.12s ease",
              borderBottom: isSelected ? "2px solid var(--border-focus)" : "2px solid transparent",
            }}
            title={def.label}
          >
            {/* 状态圆点 */}
            <span
              className={isProcessing ? "anim-spin" : isReview ? "anim-pulse" : ""}
              style={{
                width: 16, height: 16, borderRadius: "50%",
                background: dotColor, color: "#fff",
                fontSize: 9, fontWeight: 700,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {STATUS_ICON[status]}
            </span>

            <span style={{ whiteSpace: "nowrap", fontWeight: isSelected ? 600 : 400 }}>
              {def.label}
            </span>

            {/* 箭头分隔 */}
            {i < STAGES.length - 1 && (
              <span style={{
                position: "absolute", right: -6, top: "50%", transform: "translateY(-50%)",
                fontSize: 10, color: "var(--border)", zIndex: 1,
              }}>›</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
