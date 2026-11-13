"""Check production or audit language in editable narration."""
import re

PATTERN = re.compile(
    r'原稿|参考文案|改写后(?:的)?文案|作者转述|依据原稿保留|未独立核验|医学事实|因果证据'
    r'|(?:出处|来源|归属|作者身份|原文版本)(?:\s|[，、：])*'
    r'(?:尚不详|尚不明|不详|不明|'
    r'(?:(?:尚|仍)?(?:有待|待|未(?:能)?|需(?:要)?)|无法|难以)'
    r'(?:进一步|独立)?(?:核实|核验|查证|考证|确认|证实|确定))'
)


def spoken_style_issues(text: str, hook: str = '', tail: str = '') -> list[str]:
    body = text.strip()
    if hook:
        body = body.removeprefix(hook)
    if tail:
        body = body.rstrip().removesuffix(tail)
    found = list(dict.fromkeys(PATTERN.findall(body)))
    return ['口播含制作或审稿用语：' + '、'.join(found) + '；仅改写正文，保留必要事实边界'] if found else []
