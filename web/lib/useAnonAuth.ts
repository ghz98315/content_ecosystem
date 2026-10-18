"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

let connecting: Promise<string | null> | null = null;
function connectWorkspace() {
  if (!connecting) connecting = (async () => {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    if (data.session) return data.session.user.id;
    const { data: signIn, error: signInError } = await supabase.auth.signInAnonymously();
    if (signInError) throw signInError;
    return signIn.user?.id || null;
  })().finally(() => { connecting = null; });
  return connecting;
}

/** M0：匿名登录，拿到 auth.uid() 让 RLS 的 owner 策略生效。 */
export function useAnonAuth() {
  const [userId, setUserId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) { setUserId(session?.user.id || null); if (session) setError(null); }
    });
    connectWorkspace().then(id => { if (active) { setUserId(id); setError(null); } })
      .catch(error => { if (active) setError(error instanceof Error ? error.message : '工作区连接失败'); });
    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  return { userId, error };
}
