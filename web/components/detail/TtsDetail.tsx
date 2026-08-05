"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface TtsData {
  voice?: string;
  duration?: number;
  segment_count?: number;
  text?: string;
  narration_text?: string;
  cta_text?: string;
  input_format?: string;
  synthesis_batches?: number;
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
      .then(r => r.json()).then(setData).catch(() => {});

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
      {audioUrl && (
        <div style={{ marginBottom: 20 }}>
          <audio
            controls src={audioUrl}
            style={{ width: "100%", borderRadius: "var(--radius-md)" }}
          />
        </div>
      )}

      {data && (
        <>
          <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
            {[
              { label: "音色",   value: data.voice || "—" },
              { label: "时长",   value: fmtDur(data.duration) },
              { label: "片段数", value: String(data.segment_count ?? "—") },
              { label: "合成批次", value: String(data.synthesis_batches ?? "—") },
              { label: "输入格式", value: data.input_format === "plain_text_v2" ? "纯文本" : "历史格式" },
            ].map(({ label, value }) => (
              <div key={label} style={{ fontSize: 13 }}>
                <span style={{ color: "var(--text-secondary)" }}>{label}  </span>
                <span style={{ fontWeight: 600 }}>{value}</span>
              </div>
            ))}
          </div>

          {(data.narration_text || data.text) && (
            <>
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
            </>
          )}

          {data.cta_text && (
            <>
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
            </>
          )}
        </>
      )}
    </DetailShell>
  );
}
