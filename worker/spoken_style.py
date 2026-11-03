"""Check production or audit language in generated narration, excluding the locked hook."""
import re

PATTERN = re.compile(r'原稿|参考文案|改写后(?:的)?文案|作者转述|依据原稿保留|未独立核验|医学事实|因果证据')


def spoken_style_issues(text: str, hook: str = '') -> list[str]:
    body = text[len(hook):] if hook and text.startswith(hook) else text
    found = list(dict.fromkeys(PATTERN.findall(body)))
    return ['口播含制作或审稿用语：' + '、'.join(found) + '；仅改写正文，保留必要事实边界'] if found else []
