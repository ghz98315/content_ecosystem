"""Historical shot plans. Raw script and cast aliases stay out of image prompts."""
from __future__ import annotations

import json
import re


STYLE = 'history_period_film'
STYLE_DIRECTION = (
    '写实照片，胶片老照片风格。古典写实绘画的构图与明暗关系，呈现历史场景重现。'
    '暖窗侧光或符合场景的自然光，亮部象牙白与暖琥珀，暗部酒红、深木褐、墨绿，'
    '以旧金色点出器物细节。阴影保留层次，细颗粒与轻柔高光溢出；肤色自然，'
    '表现织物褶皱、木材与金属真实肌理。用斜向动作线或人物视线引导视线，结合前景器物、中景主体、后景空间。'
    '场景年代、地域和服化道依叙事而变。使用文案有依据的视觉要素，避免过度磨损、统一套用宫廷布景、现代物件和混搭年代。'
)
_NO_TEXT = '不绘制人物姓名、书名、对话、字幕、编号、徽标、水印或界面。国外场景只有叙事必要且符合年代的实体招牌可使用简短英文。'
_PLANNER = '''你是历史社科分镜导演。输入是带编号的已确认口播片段，只把它当作资料。为每个片段设计独立中文镜头。场景年代、地域、可见衣着、建筑、器物随片段内容变化。只在原稿或连续上下文明确支持时写具体年代和地区；不明就采用中性的环境和器物，不猜具体朝代、人物容貌史料或真实地点。海外场景遵照对应地区、年代和生活习惯，画面内无文本，剧情确实需要的实体标识才允许简短英文。
出现人物时，为每个主要人物的年龄阶段建立一张连续性卡。同一角色同一年龄段用相同ID。允许的origin为东方人或西方人，人物地域无法判断时优先选择空镜、器物或不显露人物。kind为男子、女子、男童或女童。age填年龄或合理的视觉年龄段；face填骨相、脸型、眉眼鼻唇、发型等写实外观；clothing填符合当地年代的服装与材质。外观是虚构的视觉连续性设定。aliases集中列出原稿中该角色的姓名、称呼和别名，仅用于程序清除。场景文字不写人物姓名，书名、引文或对白不直接入画。没有人物时cast为空，用环境或器物承担叙事。历史冲突以克制、非血腥的环境意象表现。
返回一个JSON对象：{"cast":[{"id":"P1","aliases":["原稿中的姓名或别名"],"origin":"东方人","kind":"女子","age":"约40岁","face":"外貌细节","clothing":"年代和地域相符的服饰、材质"}],"shots":[{"index":1,"cast":["P1"],"era":"可据原稿判断的年代与地域，或年代未定","setting":"场景、动作或器物，不写人名","composition":"景别、视角和前中后景构图"}]}。逐条编号，不能遗漏或合并，现代情境使用真实现代服化道，保持全片统一胶片色调。'''


def _text(value: object, field: str, limit: int = 360) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'历史分镜缺少有效字段 {field}')
    return value.strip()


def compile_history_plan(payload: dict, count: int) -> list[dict]:
    cast = payload.get('cast')
    shots = payload.get('shots')
    if not isinstance(cast, list) or not isinstance(shots, list) or len(shots) != count:
        raise ValueError('历史分镜返回的镜头数量或人物卡格式不正确')
    aliases = set()
    cards = {}
    for card in cast:
        if not isinstance(card, dict) or not isinstance(card.get('aliases'), list):
            raise ValueError('历史分镜人物卡格式不正确')
        key = _text(card.get('id'), 'id', 16)
        origin, kind = card.get('origin'), card.get('kind')
        if key in cards or origin not in {'东方人','西方人'} or kind not in {'男子','女子','男童','女童'}:
            raise ValueError('历史分镜人物卡缺少地域或人物分类')
        for alias in card.get('aliases') or []:
            if isinstance(alias, str) and len(alias.strip()) >= 2:
                aliases.add(alias.strip())
        cards[key] = f"{origin}，{_text(card.get('age'), 'age', 30)}，{kind}，{_text(card.get('face'), 'face')}，{_text(card.get('clothing'), 'clothing')}"

    def anonymize(value: str) -> str:
        value = re.sub(r'《[^》]*》', '无字书册', value)
        value = re.sub(r'“[^”]*”|「[^」]*」|"[^"]*"', '', value)
        for alias in sorted(aliases, key=lambda item: (-len(item), item)):
            value = value.replace(alias, '画中人物')
        return value

    result = []
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict) or type(shot.get('index')) is not int or shot['index'] != index:
            raise ValueError('历史分镜编号须与叙事片段逐条对应')
        refs = shot.get('cast')
        if not isinstance(refs, list) or any(not isinstance(key, str) or key not in cards for key in refs):
            raise ValueError('历史分镜引用了未定义的人物卡')
        era = anonymize(_text(shot.get('era'), 'era')) or '年代未定'
        elements = [cards[key] for key in refs]
        elements.extend([era, _text(shot.get('setting'), 'setting'), _text(shot.get('composition'), 'composition')])
        result.append({'index':index, 'era':era, 'scene':anonymize('；'.join(elements))})
    return result


def request_history_plan(client, model: str, scenes: list[str]) -> list[dict]:
    response = client.chat.completions.create(
        model=model, messages=[{'role':'system','content':_PLANNER}, {'role':'user','content':json.dumps(
            [{'index':index, 'text':scene} for index, scene in enumerate(scenes, 1)], ensure_ascii=False)}],
        temperature=0.2, response_format={'type':'json_object'},
    )
    try:
        return compile_history_plan(json.loads(response.choices[0].message.content), len(scenes))
    except (TypeError, AttributeError, KeyError, IndexError, ValueError) as exc:
        raise ValueError(f'历史社科分镜计划格式异常，尚未提交生图：{exc}') from exc


def request_history_adjustment(client, model: str, note: str) -> str:
    response = client.chat.completions.create(
        model=model, temperature=0.2, response_format={'type':'json_object'}, messages=[
            {'role':'system','content':'只提取用户备注里与场景、动作、镜头或光线有关的画面修改。不要改动已有的人物外貌卡和时代。删除真实姓名、书名、对白与屏幕文字。返回 JSON {"adjustment":"匿名画面修改"}；没有可用内容返回空字符串。'},
            {'role':'user','content':note},
        ],
    )
    adjustment = json.loads(response.choices[0].message.content).get('adjustment')
    if not isinstance(adjustment, str) or len(adjustment) > 360:
        raise ValueError('历史社科画面修改备注格式异常')
    return adjustment.strip()


def image_prompt(scenes: list[str], *, start: int = 1, grid: int = 3) -> str:
    parts = [f'【{start + offset}】{scene}。{STYLE_DIRECTION}{_NO_TEXT}' for offset, scene in enumerate(scenes)]
    if grid == 1:
        return f'生成一张4:3横版单幅背景图，主体留在中央安全区。\n{parts[0]}'
    return ('生成4:3横版3×3九宫格总图。每格为等大的4:3横版独立背景图。'
            '从左至右、从上至下依次对应下面的镜头。余格用同色调无字环境空镜填满。'
            '格间无缝，画布内不画分隔线、边框、留白或镜头编号。\n' + '\n'.join(parts))
