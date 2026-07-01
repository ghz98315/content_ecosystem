"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";

const BUCKET = "artifacts";

interface RewriteData {
  candidates: string[];
  chosen: number | null;
}

/** 改写评审门：展示 3 个候选，用户选一个后推 pending 继续。 */
export function RewriteReview({
  taskId,
  stage,
}: {
  taskId: string;
  stage: Stage;
}) {
  const [data, setData] = useState<RewriteData | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!stage.output_ref) return;
    (async () => {
      const { data: raw, error } = await supabase.storage
        .from(BUCKET)
        .download(stage.output_ref!);
      if (error || !raw) return;
      const text = await raw.text();
      const parsed: RewriteData = JSON.parse(text);
      setData(parsed);
      // 已有历史选择则预选
      if (parsed.chosen != null) setSelected(parsed.chosen);
    })();
  }, [stage.output_ref]);

  const confirm = async () => {
    if (selected == null) { setErr("请先选择一个候选"); return; }
    setBusy(true); setErr(null);
    try {
      await supabase
        .from("stages")
        .update({
          status: "pending",
          error: null,
          params: { ...(stage.params || {}), chosen_index: selected },
        })
        .eq("id", stage.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <div style={{ fontSize: 13, color: "#6b7280", marginTop: 8 }}>加载候选中…</div>;

  return (
    <div style={S.box}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
        请选择一个改写候选，选好后点确认：
      </div>
      {data.candidates.map((text, i) => (
        <div
          key={i}
          style={{ ...S.card, ...(selected === i ? S.cardSelected : {}) }}
          onClick={() => setSelected(i)}
        >
          <div style={S.cardLabel}>候选 {["A","B","C"][i] ?? i + 1}</div>
          <pre style={S.pre}>{text}</pre>
        </div>
      ))}
      <button style={S.btn} onClick={confirm} disabled={busy || selected == null}>
        {busy ? "提交中…" : "确认继续"}
      </button>
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}

const S: Record<string, React.CSSProperties> = {
  box: { marginTop: 8 },
  card: { border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, marginBottom: 8, cursor: "pointer", background: "#fff" },
  cardSelected: { border: "2px solid #2563eb", background: "#eff6ff" },
  cardLabel: { fontSize: 12, fontWeight: 700, color: "#6b7280", marginBottom: 4 },
  pre: { margin: 0, fontSize: 13, whiteSpace: "pre-wrap", lineHeight: 1.6, fontFamily: "inherit" },
  btn: { padding: "7px 20px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 },
};
