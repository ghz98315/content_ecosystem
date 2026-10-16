"""Named production contracts; copy rewriting stays on its existing category."""
TEMPLATES = {
    'guoxue-v1': ('guoxue_gongbi_life', '4:3', 'landscape_blur'),
    'health-v1': ('warm_editorial', '9:16', 'portrait'),
    'history-v1': ('history_ink_scroll', '9:16', 'portrait'),
    'education-v1': ('clean_modern', '9:16', 'portrait'),
}


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
