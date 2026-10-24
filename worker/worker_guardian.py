"""Local liveness guard. Never claims jobs or terminates a live Worker."""
import ctypes,json,os,subprocess,threading,time
from ctypes import wintypes
from datetime import datetime,timezone
from pathlib import Path
import httpx
import db,config

ROOT=Path(__file__).resolve().parent
LOG=ROOT/'runtime-logs'
HEALTH_PATH='system/worker-health.json'

def worker_alive(state):
    if os.name!='nt':return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    handle=kernel.OpenProcess(0x1000,False,int(state.get('pid',0)))
    if not handle:return False
    try:
        exit_code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) or exit_code.value!=259:return False
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):return False
        runtime=json.loads((ROOT/'output/worker-runtime.json').read_text(encoding='utf-8-sig'))
        if os.path.normcase(buffer.value)!=os.path.normcase(runtime['python']):return False
        times=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):return False
        created=((times[0].dwHighDateTime<<32)+times[0].dwLowDateTime)/10_000_000-11644473600
        return abs(created-datetime.fromisoformat(state['started_at']).timestamp())<10
    except (ValueError,KeyError,OSError):return False
    finally:kernel.CloseHandle(handle)

def inspect_worker():
    try:state=json.loads((LOG/'worker-service.pid.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return False
    return worker_alive(state)

def service_locked():
    try:
        with (LOG/'worker-service.lock').open('a'):pass
        return False
    except PermissionError:return True

def start_service():
    # FileShare.None in the service itself is the final duplicate-launch fence.
    subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'run_worker_service.ps1')],cwd=ROOT.parent,creationflags=subprocess.CREATE_NO_WINDOW)

def guard_once(state,last_launch,now):
    alive=inspect_worker();state.update(status='online' if alive else 'recovering',checked_at=time.time())
    if not alive and not service_locked() and now-last_launch>20:
        start_service();print('Worker supervisor launched',flush=True);return now
    return last_launch

def main():
    LOG.mkdir(exist_ok=True);state={'status':'recovering','checked_at':0};last_launch=0
    def publish():
        db._use_windows_system_proxy()
        while True:
            payload={**state,'heartbeat_at':datetime.now(timezone.utc).isoformat(),'version':1}
            try:
                with httpx.Client(timeout=10) as client:
                    response=client.post(config.SUPABASE_URL+'/storage/v1/object/artifacts/'+HEALTH_PATH,headers={'apikey':config.SUPABASE_SERVICE_KEY,'Authorization':'Bearer '+config.SUPABASE_SERVICE_KEY,'x-upsert':'true','Content-Type':'application/json'},json=payload)
                    response.raise_for_status()
            except Exception as exc:print('Health publication retry:',type(exc).__name__,flush=True)
            time.sleep(20)
    threading.Thread(target=publish,daemon=True).start()
    while True:
        try:
            last_launch=guard_once(state,last_launch,time.monotonic())
        except Exception as exc:state.update(status='recovering',checked_at=time.time());print('Guard retry:',type(exc).__name__,flush=True)
        time.sleep(5)

if __name__=='__main__':main()
