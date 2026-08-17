"use client";

import { DragEvent, FormEvent, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import { Task } from "@/lib/types";

const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"]);
type VoiceProvider = "edge" | "cosyvoice2" | "indextts25";
type VoiceProfile = { id: string; display_name: string; provider: VoiceProvider; model?: string | null; voice_id: string; enabled: boolean; is_default: boolean; authorization_confirmed: boolean; sample_path?: string | null; updated_at?: string };

export default function VoiceCloningPage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [copied, setCopied] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [name, setName] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [provider, setProvider] = useState<VoiceProvider>("edge");
  const [model, setModel] = useState("cosyvoice-v3.5-flash");
  const [authorized, setAuthorized] = useState(false);
  const [profileBusyId, setProfileBusyId] = useState<string | null>(null);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => {
    supabase.from("tasks").select("*").order("created_at", { ascending: false }).limit(20).then(({ data }) => data && setTasks(data as Task[]));
    supabase.from("voice_profiles").select("*").order("updated_at", { ascending: false }).then(({ data }) => data && setProfiles(data as VoiceProfile[]));
  }, []);

  function chooseFile(next: File | null) {
    setError(""); setUrl(""); setCopied(false);
    if (!next) return setFile(null);
    if (!ALLOWED_TYPES.has(next.type.toLowerCase())) return setError("仅支持 MP3、WAV 或 M4A 音频");
    if (next.size > MAX_BYTES) return setError("音频文件不能超过 10 MB");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(next); setPreviewUrl(URL.createObjectURL(next));
  }

  function drop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files?.[0] || null); }

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setUrl("");
    if (!file) return setError("请选择音频文件");
    if (!name.trim()) return setError("请填写音色名称");
    if (!voiceId.trim()) return setError("请填写 Voice ID");
    if (!authorized) return setError("请确认拥有该声音样本的使用授权");
    setBusy(true);
    try {
      const form = new FormData(); form.set("audio", file);
      const response = await fetch("/api/voice-sample", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "上传失败");
      const { data: userData } = await supabase.auth.getUser();
      if (!userData.user) throw new Error("请先登录后再保存音色");
      const { data: profile, error: insertError } = await supabase.from("voice_profiles").insert({ owner: userData.user.id, display_name: name.trim(), provider, model: model.trim() || null, voice_id: voiceId.trim(), sample_path: result.path, authorization_confirmed: authorized }).select().single();
      if (insertError) throw insertError;
      setProfiles(current => [profile as VoiceProfile, ...current]); setName(""); setVoiceId(""); setAuthorized(false); setUrl(result.signedUrl);
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } finally { setBusy(false); }
  }

  async function toggle(profile: VoiceProfile) {
    if (profileBusyId) return;
    if (profile.is_default && profile.enabled) {
      return setError("请先把其他音色设为新任务默认，再停用当前默认音色");
    }
    if (!profile.enabled && !profile.authorization_confirmed) {
      return setError("该音色尚未确认样本授权，无法启用");
    }
    setProfileBusyId(profile.id);
    const { data, error: rpcError } = await supabase.rpc("toggle_voice_profile", { p_id: profile.id, p_enabled: !profile.enabled });
    setProfileBusyId(null);
    if (rpcError) return setError(rpcError.message);
    if (data) setProfiles(items => items.map(item => item.id === profile.id ? data as VoiceProfile : item));
  }

  async function remove(profile: VoiceProfile) {
    if (profileBusyId) return;
    if (!window.confirm(`确认删除音色“${profile.display_name}”吗？`)) return;
    setProfileBusyId(profile.id);
    const { error: rpcError } = await supabase.rpc("delete_voice_profile", { p_id: profile.id });
    setProfileBusyId(null);
    if (rpcError) return setError(rpcError.message);
    setProfiles(items => items.filter(item => item.id !== profile.id));
  }

  async function setDefault(profile: VoiceProfile) {
    if (profileBusyId || profile.is_default) return;
    if (!profile.enabled || !profile.authorization_confirmed) {
      return setError("只有已启用且已确认授权的音色才能设为新任务默认");
    }
    setProfileBusyId(profile.id);
    const { error: rpcError } = await supabase.rpc("set_default_voice_profile", { p_id: profile.id });
    setProfileBusyId(null);
    if (rpcError) return setError(rpcError.message);
    setProfiles(items => items.map(item => ({ ...item, is_default: item.id === profile.id })));
  }

  return <AppShell tasks={tasks}><div className="voice-page"><div className="voice-workspace"><section className="voice-upload-panel"><p className="eyebrow">VOICE ENROLLMENT</p><h1>音色样本与配置</h1><p className="voice-description">上传样本并保存 Provider、模型、Voice ID 与授权信息。只有已确认授权且启用的音色，才能被新任务选用。</p><form onSubmit={submit}><div className="voice-profile-fields"><input value={name} onChange={e => setName(e.target.value)} placeholder="音色名称" /><select value={provider} onChange={e => { const next = e.target.value as VoiceProvider; setProvider(next); setModel(next === "indextts25" ? "index-tts-2.5" : next === "cosyvoice2" ? "cosyvoice-v3.5-flash" : "edge-tts"); }}><option value="edge">Edge TTS</option><option value="cosyvoice2">CosyVoice2</option><option value="indextts25">IndexTTS2.5</option></select><input value={model} onChange={e => setModel(e.target.value)} placeholder="模型，例如 index-tts-2.5" /><input value={voiceId} onChange={e => setVoiceId(e.target.value)} placeholder={provider === "indextts25" ? "云端音色 profile，例如 narrator_f" : "Voice ID"} /><label><input type="checkbox" checked={authorized} onChange={e => setAuthorized(e.target.checked)} /> 我确认拥有该声音样本的使用授权</label></div><label className={`voice-dropzone ${dragging ? "is-dragging" : ""}`} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}><input hidden type="file" accept="audio/mpeg,audio/wav,audio/mp4,audio/m4a" onChange={e => chooseFile(e.target.files?.[0] || null)} /><strong>{file ? file.name : "选择或拖入音频"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "建议 10-30 秒清晰朗读，最大 10 MB"}</span></label>{previewUrl && <audio controls src={previewUrl} className="voice-preview" />}<button type="submit" disabled={busy || !file} className="primary-action voice-submit">{busy ? "正在保存…" : "保存音色配置"}</button></form>{error && <p role="alert" className="voice-error">{error}</p>}{url && <div className="voice-result"><strong>样本访问地址</strong><textarea readOnly value={url} /><button type="button" className="secondary-action" onClick={async () => { await navigator.clipboard.writeText(url); setCopied(true); }}>{copied ? "已复制" : "复制地址"}</button></div>}</section><section className="voice-profile-list"><h2>已配置音色</h2>{profiles.length === 0 ? <p className="muted">暂无音色配置</p> : profiles.map(profile => { const profileBusy = profileBusyId === profile.id; return <article key={profile.id}><div><strong>{profile.display_name}</strong><small>{profile.provider} · {profile.model || "默认模型"}</small><small>{profile.voice_id}</small><small>{profile.authorization_confirmed ? "已确认授权" : "未确认授权"} · {profile.sample_path ? "已保存样本" : "无样本文件"}</small></div><div className="voice-profile-actions"><span className={profile.is_default ? "status-done" : profile.enabled ? "status-done" : "muted"}>{profile.is_default ? "新任务默认" : profile.enabled ? "启用" : "停用"}</span><button type="button" className="secondary-action" disabled={Boolean(profileBusyId) || profile.is_default} onClick={() => setDefault(profile)}>{profile.is_default ? "已设默认" : "设为默认"}</button><button type="button" className="secondary-action" disabled={Boolean(profileBusyId)} onClick={() => toggle(profile)}>{profileBusy ? "处理中…" : profile.enabled ? "停用" : profile.authorization_confirmed ? "启用" : "需先授权"}</button><button type="button" className="secondary-action danger-action" disabled={Boolean(profileBusyId)} onClick={() => remove(profile)}>删除</button></div></article>; })}</section></div></div></AppShell>;
}
