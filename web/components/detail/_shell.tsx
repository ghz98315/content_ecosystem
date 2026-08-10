"use client";
import { Stage, Task } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  pending: "等待中", processing: "处理中", done: "完成",
  failed: "失败", needs_review: "待确认", cancelled: "已跳过",
};
const STATUS_COLOR: Record<string, string> = {
  pending: "var(--status-pending)", processing: "var(--status-processing)",
  done: "var(--status-done)", failed: "var(--status-failed)",
  needs_review: "var(--status-review)", cancelled: "var(--status-cancelled)",
};

export interface DetailCommon {
  stage: Stage | undefined;
  taskId: string;
  task: Task;
  onRerun: (id: string) => void;
  onApprove: (id: string, kind: string) => void;
}

interface ShellProps {
  title: string;
  stage: Stage | undefined;
  onRerun: (id: string) => void;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  showChildrenOnPending?: boolean;
  errorPosition?: "top" | "bottom";
  errorTone?: "error" | "warning";
}

export function DetailShell({
  title, stage, onRerun, children, actions,
  showChildrenOnPending = false,
  errorPosition = "top",
  errorTone = "error",
}: ShellProps) {
  const status = stage?.status ?? "pending";
  const color  = STATUS_COLOR[status] ?? "var(--status-pending)";
  const isPending    = status === "pending";
  const isProcessing = status === "processing";
  const isFailed     = status === "failed";
  const isCancelled  = status === "cancelled";
  const canRerun     = stage && !isPending && !isProcessing && !isCancelled;
  const diagnosticBackground = errorTone === "warning" ? "#fffbeb" : "#fff5f5";
  const diagnosticBorder = errorTone === "warning" ? "#fde68a" : "#fecaca";
  const diagnosticColor = errorTone === "warning" ? "#a16207" : "var(--status-failed)";

  return (
    <div className="detail-shell">
      {/* 标题行 */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>{title}</h2>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
          <span
            className={isProcessing ? "status-dot anim-spin" : "status-dot"}
            style={{ background: color }}
          />
          <span style={{ color }}>{STATUS_LABEL[status]}</span>
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {actions}
          {canRerun && (
            <TextBtn onClick={() => onRerun(stage!.id)}>重跑</TextBtn>
          )}
        </div>
      </div>

      {/* 错误 */}
      {errorPosition === "top" && isFailed && stage?.error && (
        <div style={{
          padding: "8px 12px", borderRadius: "var(--radius-md)",
          background: diagnosticBackground, border: `1px solid ${diagnosticBorder}`,
          color: diagnosticColor, fontSize: 12,
          fontFamily: "monospace", wordBreak: "break-all", marginBottom: 16,
        }}>
          {stage.error}
        </div>
      )}

      {/* 等待/跳过提示 */}
      {(isPending || isCancelled) && (
        <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>
          {isCancelled ? "该阶段已跳过" : "等待前置阶段完成…"}
        </p>
      )}

      {/* 主内容 */}
      {(!isCancelled && (!isPending || showChildrenOnPending)) && children}

      {errorPosition === "bottom" && isFailed && stage?.error && (
        <div style={{
          padding: "8px 12px", borderRadius: "var(--radius-md)",
          background: diagnosticBackground, border: `1px solid ${diagnosticBorder}`,
          color: diagnosticColor, fontSize: 12,
          fontFamily: "monospace", wordBreak: "break-all", marginTop: 16,
        }}>
          {stage.error}
        </div>
      )}
    </div>
  );
}

export function TextBtn({
  children, onClick, disabled, variant = "default",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "primary" | "danger";
}) {
  const bg = variant === "primary" ? "#111827" : variant === "danger" ? "#fee2e2" : "var(--bg-hover)";
  const fg = variant === "primary" ? "#fff" : variant === "danger" ? "var(--status-failed)" : "var(--text-secondary)";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "5px 14px", border: "none", borderRadius: "var(--radius-md)",
        background: disabled ? "var(--bg-hover)" : bg,
        color: disabled ? "var(--text-disabled)" : fg,
        fontSize: 13, cursor: disabled ? "not-allowed" : "pointer",
        transition: "background 0.12s ease, color 0.12s ease",
      }}
    >
      {children}
    </button>
  );
}
