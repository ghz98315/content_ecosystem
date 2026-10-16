import { supabase } from './supabase';
/** Never forward workspace tokens to signed media URLs or other origins. */
export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  if (!path.startsWith('/api/') || path.includes('\\')) throw new Error('不支持的请求地址');
  const {data,error}=await supabase.auth.getSession();
  if(error || !data.session)throw new Error('请刷新页面重新连接工作区');
  const headers=new Headers(init.headers);
  headers.set('Authorization',`Bearer ${data.session.access_token}`);
  return fetch(path,{...init,headers});
}
