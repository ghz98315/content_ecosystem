"""Private, licensed music-library paths allowed in render tasks."""

import re

PRESET_PATHS = frozenset({
    'music-presets/guoxue-yougu.mp3',
    'music-presets/guoxue-1030.mp3',
    'music-presets/health-yekong.mp3',
    'music-presets/health-qiudesi.mp3',
    'music-presets/guoxue-ripples.mp3',
    'music-presets/guoxue-ishikari-lore.mp3',
    'music-presets/guoxue-finding-movement.mp3',
    'music-presets/health-morning.mp3',
    'music-presets/health-evening.mp3',
    'music-presets/health-midsummer-sky.mp3',
})


def is_user_preset(path: str, owner: str) -> bool:
    return bool(owner and re.fullmatch(
        rf'user-music/{re.escape(owner)}/(?:guoxue|health)/[0-9a-f-]{{36}}--[A-Za-z0-9_-]+\.(?:mp3|wav|m4a)', path,
    ))
