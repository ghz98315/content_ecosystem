"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Task } from "@/lib/types";
import { DetailShell, DetailCommon } from "./_shell";

interface Meta {
  digg_count?: number;
  comment_count?: number;
  share_count?: number;
  collect_count?: number;
  duration?: number;
  hot_comments?: { text: string; likes: number; author: string; replies: number }[];
  purchase_intent_comments?: { text: string; likes: number; author: string; replies: number; purchase_intent_phrases?: string[] }[];
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      flex: 1, minWidth: 100, padding: "12px 16px",
      border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
      textAlign: "center",
    }}>
      <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function fmt(n?: number): string {
  if (n == null) return "—";
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  return n.toLocaleString();
}

function fmtDur(s?: number): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function IngestDetail({ stage, taskId, task, onRerun, onApprove }: DetailCommon & { task: Task }) {
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    supabase
      .from("artifacts")
      .select("meta")
      .eq("task_id", taskId)
      .eq("stage_kind", "ingest")
      .eq("type", "audio")
      .order("created_at", { ascending: false })
      .limit(1)
      .then(({ data }) => {
        if (data?.[0]?.meta) setMeta(data[0].meta as Meta);
      });
  }, [stage?.output_ref, taskId]);

  const author = task.author as Record<string, string> | null;

  return (
    <DetailShell title="采集" stage={stage} onRerun={onRerun}>
      {/* 视频信息 */}
      <section style={{ marginBottom: 24 }}>
        <Label>视频信息</Label>
        <Row label="标题">{task.title || "—"}</Row>
        <Row label="作者">{author?.name ? `@${author.name}` : "—"}</Row>
        <Row label="粉丝量">
          {(author as any)?.fans_count != null
            ? fmt((author as any).fans_count)
            : <span style={{ color: "var(--text-disabled)", fontSize: 12 }}>—</span>}
        </Row>
        <Row label="时长">{fmtDur(meta?.duration)}</Row>
      </section>

      {/* 数据指标 */}
      <section style={{ marginBottom: 24 }}>
        <Label>数据指标</Label>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <StatCard label="点赞数" value={fmt(meta?.digg_count ?? task.play_count ?? undefined)} />
          <StatCard label="评论数" value={fmt(meta?.comment_count)} />
          <StatCard label="分享数" value={fmt(meta?.share_count)} />
          <StatCard label="收藏数" value={fmt(meta?.collect_count)} />
        </div>
      </section>

      <section style={{ marginBottom: 24 }}>
        <Label>购买意向评论</Label>
        {!meta?.purchase_intent_comments?.length ? (
          <p style={{ fontSize: 13, color: "var(--text-disabled)" }}>暂未发现明确购买需求</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {meta.purchase_intent_comments.map((c, i) => (
              <div key={i} style={{ padding: "10px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--bg-page)" }}>
                <div style={{ fontSize: 13, color: "var(--text-primary)", marginBottom: 6, lineHeight: 1.6 }}>{c.text}</div>
                <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--text-disabled)" }}>
                  <span>@{c.author}</span><span>赞 {fmt(c.likes)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 热门评论 */}
      <section>
        <Label>热门评论</Label>
        {!meta?.hot_comments?.length ? (
          <p style={{ fontSize: 13, color: "var(--text-disabled)" }}>暂无评论数据</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {meta.hot_comments.map((c, i) => (
              <div key={i} style={{
                padding: "10px 14px",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                background: "var(--bg-page)",
              }}>
                <div style={{ fontSize: 13, color: "var(--text-primary)", marginBottom: 6, lineHeight: 1.6 }}>
                  {c.text}
                </div>
                <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--text-disabled)" }}>
                  <span>@{c.author}</span>
                  <span>❤ {fmt(c.likes)}</span>
                  {c.replies > 0 && <span>回复 {c.replies}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </DetailShell>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 600, color: "var(--text-disabled)",
      letterSpacing: "0.06em", textTransform: "uppercase",
      marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ width: 72, flexShrink: 0, color: "var(--text-secondary)", fontSize: 13 }}>{label}</span>
      <span style={{ fontSize: 13, color: "var(--text-primary)" }}>{children}</span>
    </div>
  );
}
