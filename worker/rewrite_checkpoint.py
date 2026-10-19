"""Persist bounded rewrite attempts before each request and resume after interruption."""
import hashlib,json,uuid
from pathlib import Path
import db,storage


def prepare(stage, params, source, profile, notes, mode):
    signature=hashlib.sha256(json.dumps({'source':source,'profile':profile,'notes':notes,'mode':mode},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    generation=params.get('rewrite_generation');resume=None
    if generation:
        try:
            uuid.UUID(str(generation))
            path=f"{stage['task_id']}/rewrite-progress/{generation}.json"
            local=storage.download_artifact(path,'.json')
            try: old=json.loads(Path(local).read_text(encoding='utf-8'))
            finally:Path(local).unlink(missing_ok=True)
            if old.get('signature')==signature and old.get('state')=='in_progress': resume=old
        except Exception as exc:
            # Do not resend a possibly charged request when its prior record is unavailable.
            raise RuntimeError('读取二创执行进度失败，已停止自动重新请求，请恢复连接后重试') from exc
    if resume is None:
        generation=str(uuid.uuid4());path=f"{stage['task_id']}/rewrite-progress/{generation}.json"
        resume={'signature':signature,'state':'in_progress','history':[]}
        storage.upload_bytes(path,json.dumps(resume,ensure_ascii=False).encode(),'application/json')
        result=db.get_client().table('stages').update({'params':{**params,'rewrite_generation':generation}}).eq('id',stage['id']).eq('status','processing').select('id').execute().data
        if not result:raise RuntimeError('改写节点状态已变化，未发送模型请求')
    history=resume.get('history',[])
    if not isinstance(history,list) or len(history)>4 or any(not isinstance(item,dict) or item.get('attempt')!=index+1 for index,item in enumerate(history)):
        raise RuntimeError('二创执行进度格式无效，未发送模型请求')
    def save(history,state='in_progress'):
        payload={'signature':signature,'state':state,'history':history}
        storage.upload_bytes(path,json.dumps(payload,ensure_ascii=False).encode(),'application/json')
        storage.add_artifact(stage['task_id'],'rewrite','rewrite_checkpoint',path,meta={'state':state,'attempts':len(history),'max_attempts':4})
        save.last_history = history
    save.last_history = history
    return history,save
