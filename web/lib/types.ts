// 8 阶段定义（与 worker/supabase 保持一致；tts 在 book 之后）
export const STAGES = [
  { kind: "ingest",     label: "采集" },
  { kind: "transcribe", label: "逐字稿" },
  { kind: "clean",      label: "清洗" },
  { kind: "rewrite",    label: "改写" },
  { kind: "image",      label: "生图" },
  { kind: "book",       label: "书籍信息" },
  { kind: "tts",        label: "配音" },
  { kind: "render",     label: "成片" },
] as const;

export type StageKind = (typeof STAGES)[number]["kind"];

export type StageStatus =
  | "pending"
  | "processing"
  | "done"
  | "failed"
  | "needs_review"
  | "cancelled";

export interface Task {
  id: string;
  source_url: string | null;
  title: string | null;
  play_count: number | null;
  author: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Stage {
  id: string;
  task_id: string;
  kind: StageKind;
  seq: number;
  status: StageStatus;
  params: Record<string, unknown>;
  input_ref: string | null;
  output_ref: string | null;
  error: string | null;
  updated_at: string;
}

export const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "待处理",
  processing: "处理中",
  done: "完成",
  failed: "失败",
  needs_review: "待确认",
  cancelled: "已取消",
};

export const STATUS_COLOR: Record<StageStatus, string> = {
  pending: "#9ca3af",
  processing: "#2563eb",
  done: "#16a34a",
  failed: "#dc2626",
  needs_review: "#d97706",
  cancelled: "#6b7280",
};
