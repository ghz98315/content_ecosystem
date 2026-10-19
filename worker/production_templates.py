"""Named production contracts; copy rewriting stays on its existing category."""
import json
from pathlib import Path

# The same manifest is imported by web/lib/productionTemplates.ts.
DEFINITIONS = {item['id']: item for item in json.loads(
    (Path(__file__).resolve().parents[1] / 'web/lib/productionTemplateManifest.json').read_text(encoding='utf-8'))}
TEMPLATES = {key: (item['style'], item['aspect'], item['frameMode']) for key,item in DEFINITIONS.items()}



def inherit_template(current: dict, source: dict, kind: str) -> dict:
    """Copy only the template contract, never old jobs, pictures or titles."""
    if current.get('production_template') or not source.get('production_template'):
        return current
    keys = {'production_template', 'template_version'}
    keys |= ({'visual_style','visual_preset_id','image_aspect_ratio','image_provider','image_model'}
             if kind == 'image' else {'frame_mode','title_font','title_color'})
    result = {**current, **{key: source[key] for key in keys if key in source}}
    validate_template(result, kind)
    return result


def validate_template(params: dict, kind: str) -> None:
    template = params.get('production_template')
    if not template:  # Existing tasks retain their original snapshot.
        return
    if template not in TEMPLATES or params.get('template_version') != 1:
        raise ValueError('未支持的成片模板版本，请检查任务配置')
    style, aspect, frame_mode = TEMPLATES[template]
    expected = {'visual_style': style, 'image_aspect_ratio': aspect} if kind == 'image' else {'frame_mode': frame_mode}
    if any(params.get(key) != value for key, value in expected.items()):
        raise ValueError('内容模板与画面配置不一致，已停止以避免不同内容类型混用')


def validate_task_template(stage: dict) -> None:
    """Check the image and render snapshots agree before spending or encoding."""
    if not (stage.get('params') or {}).get('production_template'):
        return
    import db
    rows = db.retry(lambda: db.get_client().table('stages').select('kind,params')
                    .eq('task_id',stage['task_id']).in_('kind',['image','render']).execute()).data or []
    snapshots = {row['kind']: row.get('params') or {} for row in rows}
    if set(snapshots) != {'image','render'}:
        raise ValueError('画面模板快照不完整，请重新保存任务模板')
    for kind,params in snapshots.items():
        validate_template(params,kind)
    if snapshots['image'].get('production_template') != snapshots['render'].get('production_template'):
        raise ValueError('生图与成片模板不一致，请统一后重试；已有产物已保留')
