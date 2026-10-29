"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    void supabase.auth.getUser().then(({ data }) => { if (active) setUser(data.user); });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) setUser(session?.user ?? null);
    });
    return () => { active = false; listener.subscription.unsubscribe(); };
  }, []);

  const bindEmail = async () => {
    const target = email.trim().toLowerCase();
    if (!target || !user?.is_anonymous) return;
    setBusy(true); setMessage("");
    const { error } = await supabase.auth.updateUser({ email: target }, { emailRedirectTo: `${window.location.origin}/account` });
    setBusy(false);
    setMessage(error ? `绑定邮件发送失败：${error.message}` : `验证邮件已发送到 ${target}。请在邮箱中完成验证，再回到此页面查看状态。`);
  };

  const signIn = async () => {
    const target = email.trim().toLowerCase();
    if (!target) return;
    setBusy(true); setMessage("");
    const { error } = await supabase.auth.signInWithOtp({
      email: target,
      options: { shouldCreateUser: false, emailRedirectTo: `${window.location.origin}/account` },
    });
    setBusy(false);
    setMessage(error ? `登录邮件发送失败：${error.message}` : `登录邮件已发送到 ${target}，请打开邮件中的链接。`);
  };

  const signOut = async () => {
    setBusy(true); setMessage("");
    const { error } = await supabase.auth.signOut();
    setBusy(false);
    setMessage(error ? error.message : "已退出账号。请在此页重新登录；离开本页后，工作台可能会创建新的匿名空间。");
  };

  return <AppShell><main className="account-page">
    <p className="eyebrow">映作工作台 / ACCOUNT</p>
    <h1>账号管理</h1>
    {user?.is_anonymous ? <section className="account-card">
      <h2>绑定当前工作区</h2>
      <p>请在能看到原有项目的这个浏览器中绑定邮箱。完成邮件验证后，旧项目会继续保留在同一账号下。</p>
      <label>邮箱地址<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)}/></label>
      <button className="primary-action" disabled={busy || !email.trim()} onClick={bindEmail}>{busy ? "发送中…" : "发送绑定邮件"}</button>
      <small>当前工作区 ID：{user.id}</small>
      <p>已有绑定好的账号？可用邮箱登录。登录其他账号后，当前未绑定的匿名项目不会自动转移。</p>
      <button className="secondary-action" disabled={busy || !email.trim()} onClick={signIn}>使用此邮箱登录已有账号</button>
    </section> : user ? <section className="account-card">
      <h2>已登录</h2><p>{user.email || "已绑定账号"}</p><small>工作区 ID：{user.id}</small>
      <button className="secondary-action" disabled={busy} onClick={signOut}>退出登录</button>
    </section> : <section className="account-card">
      <h2>邮箱登录</h2>
      <p>输入已绑定的邮箱，使用邮件中的登录链接进入原工作区。</p>
      <label>邮箱地址<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)}/></label>
      <button className="primary-action" disabled={busy || !email.trim()} onClick={signIn}>{busy ? "发送中…" : "发送登录邮件"}</button>
    </section>}
    {message && <p className="task-notice" role="status">{message}</p>}
  </main></AppShell>;
}
