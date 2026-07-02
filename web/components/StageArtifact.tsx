"use client";
import { useEffect, useState } from "react";
import { StageKind } from "@/lib/types";

type Artifact =
  | { type: "audio"; url: string }
  | { type: "video"; url: string }
  | { type: "text"; label: string; content: string }
  | { type: "book"; fields: [string, string][] }
  | { type: "images"; items: { path: string; sentence: string }[] };

async function getSignedUrl(path: string): Promise<string> {
  const res = await fetch(`/api/signed-url?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error("获取链接失败");
  const { signedUrl } = await res.json();
  return signedUrl;
}

function ImageThumb({ path, sentence }: { path: string; sentence: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    getSignedUrl(path).then(setUrl).catch(() => {});
  }, [path]);
  if (!url) return <div style={{ width: 80, height: 80, background: "#f3f4f6", borderRadius: 4 }} />;
  return (
    <img
      src={url}
      alt={sentence}
      title={sentence}
      style={{ width: 80, height: 80, objectFit: "cover", borderRadius: 4 }}
    />
  );
}

export function StageArtifact({ kind, outputRef }: { kind: StageKind; outputRef: string }) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!outputRef || outputRef.startsWith("m0-fake")) return;
    setArtifact(null);
    setErr(null);

    (async () => {
      try {
        const ext = outputRef.split(".").pop()?.toLowerCase();
        const signedUrl = await getSignedUrl(outputRef);

        if (ext === "mp3") {
          setArtifact({ type: "audio", url: signedUrl });
          return;
        }
        if (ext === "mp4") {
          setArtifact({ type: "video", url: signedUrl });
          return;
        }

        // JSON — parse and render by kind
        const data = await fetch(signedUrl).then(r => r.json());

        if (kind === "transcribe") {
          setArtifact({ type: "text", label: "识别文字", content: data.text ?? "" });
        } else if (kind === "clean") {
          setArtifact({ type: "text", label: "清洗后文案", content: data.cleaned ?? "" });
        } else if (kind === "rewrite") {
          const idx = data.chosen ?? 0;
          const text = data.candidates?.[idx] ?? data.candidates?.[0] ?? "";
          setArtifact({ type: "text", label: `已选候选 ${["A","B","C"][idx] ?? idx+1}`, content: text });
        } else if (kind === "book") {
          const fields: [string, string][] = [
            ["书名", data.book_name ?? ""],
            ["作者", data.author ?? ""],
            ["国籍", data.nationality ?? ""],
            ["主题", data.theme ?? ""],
            ["长标题", data.title_long ?? ""],
            ["短标题", data.title_short ?? ""],
          ].filter(([, v]) => v) as [string, string][];
          setArtifact({ type: "book", fields });
        } else if (kind === "image") {
          const items: { path: string; sentence: string }[] = (
            Array.isArray(data) ? data : []
          ).slice(0, 9);
          setArtifact({ type: "images", items });
        } else {
          // fallback: show raw JSON
          setArtifact({ type: "text", label: "产物", content: JSON.stringify(data, null, 2) });
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [outputRef, kind]);

  if (!outputRef || outputRef.startsWith("m0-fake")) return null;
  if (err) return <div style={{ fontSize: 12, color: "#dc2626", marginTop: 4 }}>{err}</div>;
  if (!artifact) return <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>加载产物…</div>;

  if (artifact.type === "audio") {
    return (
      <audio
        controls
        src={artifact.url}
        style={{ width: "100%", marginTop: 6, height: 36 }}
      />
    );
  }

  if (artifact.type === "video") {
    return (
      <video
        controls
        src={artifact.url}
        style={{ width: "100%", marginTop: 6, borderRadius: 6, maxHeight: 320 }}
      />
    );
  }

  if (artifact.type === "text") {
    return (
      <div style={{ marginTop: 6 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", marginBottom: 3 }}>
          {artifact.label}
        </div>
        <pre style={{
          fontSize: 12, color: "#374151", background: "#f9fafb",
          padding: "8px 10px", borderRadius: 5, margin: 0,
          whiteSpace: "pre-wrap", lineHeight: 1.5,
          maxHeight: 180, overflow: "auto",
          fontFamily: "inherit",
        }}>
          {artifact.content}
        </pre>
      </div>
    );
  }

  if (artifact.type === "book") {
    return (
      <table style={{ fontSize: 12, color: "#6b7280", borderCollapse: "collapse", marginTop: 6, width: "100%" }}>
        <tbody>
          {artifact.fields.map(([label, val]) => (
            <tr key={label}>
              <td style={{ padding: "2px 8px 2px 0", fontWeight: 600, whiteSpace: "nowrap", verticalAlign: "top" }}>{label}</td>
              <td style={{ padding: "2px 0", lineHeight: 1.5 }}>{val}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (artifact.type === "images") {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
        {artifact.items.map((item, i) => (
          <ImageThumb key={i} path={item.path} sentence={item.sentence} />
        ))}
      </div>
    );
  }

  return null;
}
