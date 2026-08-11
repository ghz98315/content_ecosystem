"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface TtsData {
  provider?: string;
  model?: string;
  voice?: string;
  duration?: number;
  segment_count?: number;
  text?: string;
  narration_text?: string;
  cta_text?: string;
  input_format?: string;
  synthesis_batches?: number;
  subtitle_max_chars?: number;
  segments?: Array<{ text: string; start: number; end: number; char_count?: number }>;
  batches?: Array<{
    index: number;
    text: string;
    duration: number;
    start: number;
    end: number;
    path: string;
    status: string;
    audioUrl?: string;
  }>;
}

export function TtsDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [data, setData]     = useState<TtsData | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    // 加载字幕/元数据 JSON
    const subsPath = stage.output_ref.replace("tts.mp3", "tts_subtitles.json");
    fetch(`/api/signed-url?path=${encodeURIComponent(subsPath)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json()).then(async (payload: TtsData) => {
        const batches = await Promise.all((payload.batches ?? []).map(async batch => {
          try {
            const response = await fetch(`/api/signed-url?path=${encodeURIComponent(batch.path)}`);
            const { signedUrl } = await response.json();
            return { ...batch, audioUrl: signedUrl as string };
          } catch {
            return batch;
          }
        }));
        setData({ ...payload, batches });
      }).catch(() => {});

    // 加载音频
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => setAudioUrl(signedUrl))
      .catch(() => {});
  }, [stage?.output_ref]);

  function fmtDur(s?: number) {
    if (!s) return "—";
    return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  }

  return (
    <DetailShell title="配音" stage={stage} onRerun={onRerun}>
      {data && (
        <section className="media-workbench-heading tts-workbench-heading">
          <div><p className="eyebrow">AUDIO</p><h2>音频生成与时长预估</h2><p>使用当前任务快照中的 Provider、音色和语速生成配音，并按真实边界校准字幕。</p></div>
          <div className="media-workbench-actions"><span className="status-badge status-done">{data.input_format === "timeline_v3" ? "时间轴已对齐" : "已生成音频"}</span></div>
        </section>
      )}
      {audioUrl && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>完整配音</div>
          <audio
            controls src={audioUrl}
            style={{ width: "100%", borderRadius: "var(--radius-md)" }}
          />
        </div>
      )}

      {data && (
        <>
          <div className="tts-summary-grid">
            {[
              { label: "Provider", value: data.provider || "任务配置" },
              { label: "模型", value: data.model || "—" },
              { label: "音色",   value: data.voice || "—" },
              { label: "时长",   value: fmtDur(data.duration) },
              { label: "片段数", value: String(data.segment_count ?? "—") },
              { label: "合成批次", value: String(data.synthesis_batches ?? "—") },
              { label: "字幕上限", value: data.subtitle_max_chars ? `${data.subtitle_max_chars} 字` : "—" },
              { label: "时间轴", value: data.input_format === "timeline_v3" ? "已对齐" : "历史格式" },
            ].map(({ label, value }) => (
              <div key={label} className="tts-metric" style={{ fontSize: 13 }}>
                <div style={{ color: "var(--text-secondary)", fontSize: 11, marginBottom: 3 }}>{label}</div>
                <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{value}</div>
              </div>
            ))}
          </div>

          {(data.batches ?? []).length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>分段配音</div>
              <div style={{ borderTop: "1px solid var(--border)" }}>
                {(data.batches ?? []).map(batch => (
                  <div
                    key={batch.index}
                    style={{
                      display: "grid", gridTemplateColumns: "72px minmax(0, 1fr)", gap: 12,
                      padding: "12px 0", borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.7 }}>
                      <div>第 {batch.index + 1} 段</div>
                      <div>{batch.duration.toFixed(1)} 秒</div>
                      <div style={{ color: "var(--status-done)" }}>{batch.status === "done" ? "已完成" : batch.status}</div>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 8 }}>{batch.text}</div>
                      {batch.audioUrl && <audio controls src={batch.audioUrl} style={{ width: "100%", height: 32 }} />}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="tts-text-grid">
          {(data.narration_text || data.text) && (
            <section className="tts-text-panel">
              <div style={{
                fontSize: 11, fontWeight: 600, color: "var(--text-disabled)",
                letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8,
              }}>
                配音正文
              </div>
              <pre style={{
                whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 13,
                color: "var(--text-primary)", fontFamily: "var(--font)",
                background: "var(--bg-hover)", padding: 16,
                borderRadius: "var(--radius-lg)", maxHeight: 320, overflowY: "auto",
              }}>
                {data.narration_text || data.text}
              </pre>
            </section>
          )}

          {data.cta_text && (
            <section className="tts-text-panel">
              <div style={{
                fontSize: 11, fontWeight: 600, color: "var(--text-disabled)",
                letterSpacing: "0.06em", margin: "16px 0 8px",
              }}>
                收尾 CTA
              </div>
              <pre style={{
                whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 13,
                color: "var(--text-primary)", fontFamily: "var(--font)",
                background: "var(--bg-hover)", padding: 16,
                borderRadius: "var(--radius-lg)", maxHeight: 180, overflowY: "auto",
              }}>
                {data.cta_text}
              </pre>
            </section>
          )}
          </div>
        </>
      )}
    </DetailShell>
  );
}
