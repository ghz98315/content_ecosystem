"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

/** M0：匿名登录，拿到 auth.uid() 让 RLS 的 owner 策略生效。 */
export function useAnonAuth() {
  const [userId, setUserId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const { data } = await supabase.auth.getSession();
      if (data.session) {
        if (active) setUserId(data.session.user.id);
        return;
      }
      const { data: signIn, error } = await supabase.auth.signInAnonymously();
      if (error) {
        if (active) setError(error.message);
        return;
      }
      if (active) setUserId(signIn.user?.id ?? null);
    })();
    return () => {
      active = false;
    };
  }, []);

  return { userId, error };
}
