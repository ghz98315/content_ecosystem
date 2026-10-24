export function workerHealthStatus(value: {status?:string;heartbeat_at?:string;checked_at?:number}|null,now=Date.now()) {
  const published=Date.parse(value?.heartbeat_at||'');const checked=Number(value?.checked_at)*1000;
  const fresh=Number.isFinite(published)&&Number.isFinite(checked)&&now-published<75_000&&now-checked<75_000&&published<=now+30_000&&checked<=now+30_000;
  const status=fresh?(value?.status==='online'?'online':'recovering'):'unavailable';
  return {status,autoRecoveryEnabled:fresh,message:status==='online'?'Worker 在线，正常执行':status==='recovering'?'守护程序在线，正在自动恢复 Worker':'本机守护程序暂未连接；请确认电脑已开机、登录且联网'};
}
