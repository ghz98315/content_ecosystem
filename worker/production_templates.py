"""Named production contracts with independent, snapshotted content lines."""
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
    keys = {'production_template', 'template_version', 'content_line', 'visual_mode'}
    keys |= ({'visual_style','visual_preset_id','image_aspect_ratio','image_provider','image_model','grid_resolution','stock_visual_policy'}
             if kind == 'image' else {'frame_mode','title_font','title_color'})
    result = {**current, **{key: source[key] for key in keys if key in source}}
    validate_template(result, kind)
    return result


def validate_template(params: dict, kind: str) -> None:
    template = params.get('production_template')
    if not template:  # Existing tasks retain their original snapshot.
        return
    version=params.get('template_version')
    supported_versions = {1, 2, 3} if template == 'guoxue-v1' else ({1, 2} if template == 'health-v1' else {1})
    if template not in TEMPLATES or version not in supported_versions:
        raise ValueError('未支持的成片模板版本，请检查任务配置')
    style, aspect, frame_mode = TEMPLATES[template]
    if template == 'guoxue-v1' and version == 1:
        aspect='4:3'
    if template == 'guoxue-v1' and version == 2:
        aspect='1:1'
    if template == 'health-v1' and version == 1:
        aspect, frame_mode = '9:16', 'portrait'
    expected = {'visual_style': style, 'image_aspect_ratio': aspect} if kind == 'image' else {'frame_mode': frame_mode}
    if any(params.get(key) != value for key, value in expected.items()):
        raise ValueError('内容模板与画面配置不一致，已停止以避免不同内容类型混用')
    if kind == 'image' and template == 'guoxue-v1' and params.get('grid_resolution', '4k') not in {'2k', '4k'}:
        raise ValueError('国学四宫格分辨率配置无效')
    line = params.get('content_line')
    if line and line != DEFINITIONS[template]['category']:
        raise ValueError('内容类型与成片模板不一致，请检查任务配置')


def validate_task_template(stage: dict) -> None:
    """Check the image and render snapshots agree before spending or encoding."""
    if not (stage.get('params') or {}).get('production_template'):
        return
    import db
    rows = db.retry(lambda: db.get_client().table('stages').select('kind,params')
                    .eq('task_id',stage['task_id']).in_('kind',['image','render','rewrite']).execute()).data or []
    snapshots = {row['kind']: row.get('params') or {} for row in rows}
    if not {'image','render'} <= set(snapshots):
        raise ValueError('画面模板快照不完整，请重新保存任务模板')
    for kind in ('image','render'):
        validate_template(snapshots[kind],kind)
    modes=[snapshots[kind].get('visual_mode','ai_images') for kind in ('image','render')]
    if modes[0]!=modes[1] or modes[0] not in {'ai_images','stock_video'}:
        raise ValueError('素材与成片的画面来源不一致，请重新保存任务配置')
    if snapshots['image'].get('production_template') != snapshots['render'].get('production_template'):
        raise ValueError('生图与成片模板不一致，请统一后重试；已有产物已保留')
    if snapshots['image'].get('template_version') != snapshots['render'].get('template_version'):
        raise ValueError('生图与成片模板版本不一致，请统一后重试；已有产物已保留')
    line = snapshots['image'].get('content_line')
    if line:
        if snapshots['render'].get('content_line') != line or snapshots.get('rewrite',{}).get('content_line') != line:
            raise ValueError('文案、图片与成片内容类型不一致，请重新配置任务')
        selected = snapshots['rewrite'].get('rewrite_domain')
        if (line in ('guoxue','health') and selected not in (line,'mixed')) or (line == 'scene' and selected != 'scene'):
            raise ValueError('二创规则与任务内容类型不一致，请检查二创领域')
        task = db.retry(lambda: db.get_client().table('tasks').select('content_category')
                        .eq('id',stage['task_id']).single().execute()).data or {}
        database_category = DEFINITIONS[snapshots['image']['production_template']].get('databaseCategory',line)
        if task.get('content_category') not in {line,database_category}:
            raise ValueError('任务内容类型与画面模板不一致，请重新配置任务')
