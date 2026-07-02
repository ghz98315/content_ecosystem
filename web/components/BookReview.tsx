"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";

interface BookData {
  book_name: string;
  author: string;
  nationality: string;
  theme: string;
  title_long: string;
  title_short: string;
  confidence: "high" | "medium" | "low";
}

export function BookReview({ stage }: { stage: Stage }) {
  const [data, setData] = useState<BookData | null>(null);
  const [bookName, setBookName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!stage.output_ref) return;
    (async () => {
      const res = await fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref!)}`);
      if (!res.ok) { setErr("获取书籍信息失败"); return; }
      const { signedUrl } = await res.json();
      const resp = await fetch(signedUrl);
      if (!resp.ok) { setErr("下载书籍信息失败"); return; }
      const parsed: BookData = await resp.json();
      setData(parsed);
      setBookName(parsed.book_name);
    })();
  }, [stage.output_ref]);

  const confirm = async () => {
    if (!data) return;
    setBusy(true); setErr(null);
    try {
      const changed = bookName.trim() !== data.book_name;
      const patch = changed
        ? { status: "pending", error: null, params: { ...(stage.params || {}), manual_book_name: bookName.trim() } }
        : { status: "done", error: null };
      await supabase.from("stages").update(patch).eq("id", stage.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!data && !err)
    return <div style={{ fontSize: 13, color: "#6b7280", marginTop: 8 }}>加载书籍信息中…</div>;
  if (err)
    return <div style={{ fontSize: 13, color: "#dc2626", marginTop: 8 }}>{err}</div>;

  const rows: [string, string][] = [
    ["作者", data!.author],
    ["国籍", data!.nationality],
    ["主题", data!.theme],
    ["长标题", data!.title_long],
    ["短标题", data!.title_short],
  ];

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ marginBottom: 8 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>书名（可修改）</label>
        <input
          value={bookName}
          onChange={e => setBookName(e.target.value)}
          style={{
            display: "block", width: "100%", marginTop: 4, padding: "5px 8px",
            fontSize: 13, border: "1px solid #d1d5db", borderRadius: 5,
            boxSizing: "border-box",
          }}
        />
      </div>
      <table style={{ fontSize: 12, color: "#6b7280", borderCollapse: "collapse", width: "100%", marginBottom: 10 }}>
        <tbody>
          {rows.map(([label, val]) => (
            <tr key={label}>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: 600, whiteSpace: "nowrap", verticalAlign: "top" }}>{label}</td>
              <td style={{ padding: "2px 0", lineHeight: 1.5 }}>{val}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        style={{ padding: "7px 20px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}
        onClick={confirm}
        disabled={busy || !bookName.trim()}
      >
        {busy ? "提交中…" : "确认继续"}
      </button>
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}
