"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";

interface RewriteData {
  candidates: string[];
  chosen: number | null;
}

export function RewriteReview({ taskId, stage }: { taskId: string; stage: Stage }) {
  const [data, setData] = useState<RewriteData | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!stage.output_ref) return;
    (async () => {
      const res = await fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref!)}`);
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        setErr("获取候选内容失败：" + (e.error ?? res.status));
        return;
      }
      const { signedUrl } = await res.json();
      const resp = await fetch(signedUrl);
      if (!resp.ok) { setErr("下载候选内容失败"); return; }
      const parsed: RewriteData = await resp.json();
      setData(parsed);
      if (parsed.chosen != null) setSelected(parsed.chosen);
    })();
  }, [stage.output_ref]);

  const confirm = async () => {
    if (selected == null) { setErr("请先选择一个候选"); return; }
    setBusy(true); setErr(null);
    try {
      const { error: sbErr } = await supabase
        .from("stages")
        .update({ status: "pending", error: null, params: { ...(stage.params || {}), chosen_index: selected } })
        .eq("id", stage.id);
      if (sbErr) throw new Error(sbErr.message);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data && !err)
    return <div style={{ fontSize: 13, color: "#6b7280", marginTop: 8 }}>加载候选中…</div>;

  if (err)
    return <div style={{ fontSize: 13, color: "#dc2626", marginTop: 8 }}>{err}</div>;

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>选一个改写候选后点确认：</div>
      {data!.candidates.map((text, i) => (
        <div
          key={i}
          style={{
            border: selected === i ? "2px solid #2563eb" : "1px solid #e5e7eb",
            borderRadius: 8, padding: 12, marginBottom: 8, cursor: "pointer",
            background: selected === i ? "#eff6ff" : "#fff",
          }}
          onClick={() => setSelected(i)}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: "#6b7280", marginBottom: 4 }}>
            候选 {["A", "B", "C"][i] ?? i + 1}
          </div>
          <pre style={{ margin: 0, fontSize: 13, whiteSpace: "pre-wrap", lineHeight: 1.6, fontFamily: "inherit" }}>
            {text}
          </pre>
        </div>
      ))}
      <button
        style={{ padding: "7px 20px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}
        onClick={confirm}
        disabled={busy || selected == null}
      >
        {busy ? "提交中…" : "确认继续"}
      </button>
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}
