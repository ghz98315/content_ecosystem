"""Scene-only image stage with resumable four-grid bodies and a separate cover."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
from PIL import Image
import config
import db
import storage
from scene_visuals import storyboard, plan_visuals, grid_prompt


def run(stage: dict):
    from stages.image import _find_chosen_text, _generate_grid_bytes, _split_grid, _existing_image_artifacts
    task_id = stage['task_id']
    params = stage.get('params') or {}
    text = (_find_chosen_text(task_id, stage) or '').strip()
    shots = storyboard(text)
    signature = hashlib.sha256((text + str(params.get('generation_id','')) + 'scene-1.0').encode()).hexdigest()[:20]
    root = f'{task_id}/scene/{signature}'
    existing = _existing_image_artifacts(task_id)
    plan_path = root + '/visual-plan.json'
    if plan_path in existing:
        local = storage.download_artifact(plan_path,'.json')
        try:
            plan = json.loads(Path(local).read_text(encoding='utf-8'))
        finally:
            Path(local).unlink(missing_ok=True)
    else:
        context = {**db.get_task_prompt_context(task_id), 'scene_facts':params.get('scene_facts',[])}
        plan = plan_visuals(text, shots, context)
        from stages.render import _load_json_artifact
        rewrite = _load_json_artifact(task_id, 'rewrite') or {}
        if len(rewrite.get('cover_options') or []) == 3:
            plan['cover_options'] = rewrite['cover_options']
        storage.upload_bytes(plan_path, json.dumps(plan,ensure_ascii=False).encode(), 'application/json')
        storage.add_artifact(task_id,'image','scene_visual_plan',plan_path,meta={'source_sha256':plan['source_sha256'],'cover_options':plan['cover_options'],'rule_version':'scene-1.0'})
    client, model = config.image_client(str(params.get('image_provider') or config.IMAGE_PROVIDER))
    cover_path = root + '/cover.png'
    if cover_path not in existing:
        raw = _generate_grid_bytes(client, model, plan['cover_prompt'] + '；9:16竖幅，无文字与水印，非网格，单张完整创意封面。',
                                   stage_id=stage['id'],batch_key=signature+'_cover',size='9:16',resolution='2k')
        with Image.open(io.BytesIO(raw)) as image:
            width,height=image.size
        storage.upload_bytes(cover_path,raw,'image/png')
        storage.add_artifact(task_id,'image','cover_image',cover_path,meta={'role':'independent_cover','source_size':[width,height],
                             'prompt':plan['cover_prompt'],'production_template':'scene-v1'})
    index=[]
    for start in range(0,len(shots),4):
        batch=shots[start:start+4]
        grid_path=f'{root}/grid_{start//4:03d}.png'
        prompt=grid_prompt([plan['shots'][s['index']]['prompt'] for s in batch])
        paths=[f"{root}/img_{s['index']:03d}.png" for s in batch]
        if not all(path in existing for path in paths):
            if grid_path in existing:
                local=storage.download_artifact(grid_path,'.png')
                try: raw=Path(local).read_bytes()
                finally: Path(local).unlink(missing_ok=True)
            else:
                raw=_generate_grid_bytes(client,model,prompt,stage_id=stage['id'],batch_key=signature+f'_grid_{start//4}',size='9:16',resolution='2k')
                storage.upload_bytes(grid_path,raw,'image/png')
                with Image.open(io.BytesIO(raw)) as image: size=list(image.size)
                storage.add_artifact(task_id,'image','image_grid',grid_path,meta={'grid':'2x2','source_size':size,'prompt':prompt,
                                     'requested_resolution':'2k','production_template':'scene-v1'})
            pieces=_split_grid(raw,len(batch),grid_cells=2,cell_ratio=9/16,source_ratio=9/16)
            for shot,path,piece in zip(batch,paths,pieces):
                if path not in existing:
                    storage.upload_bytes(path,piece,'image/png')
                    with Image.open(io.BytesIO(piece)) as image: size=list(image.size)
                    storage.add_artifact(task_id,'image','image',path,meta={**shot,**plan['shots'][shot['index']],
                                         'cell_ratio':'9:16','source_grid':grid_path,'source_size':size,'production_template':'scene-v1'})
        for shot,path in zip(batch,paths):
            index.append({**shot,**plan['shots'][shot['index']],'path':path,'cover_path':cover_path,
                          'cover_options':plan['cover_options'],'cell_ratio':'9:16','source_grid':grid_path})
    index_path=root+'/images_index.json'
    storage.upload_bytes(index_path,json.dumps(index,ensure_ascii=False,indent=2).encode(),'application/json')
    storage.add_artifact(task_id,'image','image_index',index_path,meta={'total':len(index),'narration_char_count':sum(s['char_count'] for s in shots),
                         'production_template':'scene-v1','visual_plan':plan_path,'cover_options':plan['cover_options'],'lossless_text':True})
    return 'done',index_path


def replace_image(request: dict, entry: dict, params: dict) -> str:
    from stages.image import _generate_grid_bytes, _split_grid, _replacement_path
    index=int(request['image_index'])
    client,model=config.image_client(str(params.get('image_provider') or config.IMAGE_PROVIDER))
    prompt=(str(entry.get('prompt') or entry.get('sentence') or '') + '\n额外修正要求：'+str(request.get('note') or '')
            +'\n只生成一张完整9:16写实场景照片风格图片，不生成宫格，不混入工笔画、书籍或健康生活插画，无文字水印。')
    raw=_generate_grid_bytes(client,model,prompt,stage_id=request['stage_id'],batch_key=f"scene_replace_{request['id']}",size='9:16',resolution='2k')
    piece=_split_grid(raw,1,grid_cells=1,cell_ratio=9/16,source_ratio=9/16)[0]
    path=_replacement_path(request['task_id'],index)
    storage.upload_bytes(path,piece,'image/png')
    storage.add_artifact(request['task_id'],'image','image_replacement',path,meta={'index':index,'source_image':entry.get('path'),
                         'replacement_request_id':request['id'],'prompt':prompt,'cell_ratio':'9:16','production_template':'scene-v1'})
    return path
