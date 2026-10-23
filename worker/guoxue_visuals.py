"""Classical gongbi and light ink direction, independent of copy rewriting."""
from __future__ import annotations

import re

STYLE_ID = 'guoxue_gongbi_life'
BASE = (
    '古典工笔淡墨风，中国古代文人叙事插画，面向55至65岁国学观众。'
    '米灰与暖米白熟宣纸细腻肌理，精细柔韧墨线勾勒人物，松树枝干用苍劲墨笔，山水淡墨层染；'
    '低饱和淡彩，以灰褐、米白、墨黑为主，少量青绿和远山灰蓝点缀，避免通幅浓黄滤镜。'
    '柔和月光或自然天光，层次清楚、淡雅通透、静谧含蓄，保留纸面呼吸感。'
    '人物面容写实温厚，古代文士束发髻、宽袖交领素色长袍，衣纹细线清晰，手部自然；'
    '服饰、木案、卷轴、笔砚、松竹与远山属于统一古代语境，不出现近现代服饰和器物。'
    '这是文案哲理的古代生活视觉演绎，不把现代生活事件伪装成史实，不在图中重现社保房贷等现代物件。'
    '前景案头器物、中景文士动作、后景松竹月色或山水形成疏密纵深；完整交代人物和环境。'
)
NEGATIVE = (
    '严禁Nike、Swoosh、Adidas、品牌Logo、商标、运动鞋、球鞋、胶底鞋、背包、双肩包、斜挎包、'
    '塑料水杯、保温杯、矿泉水瓶、现代手表、T恤、卫衣、牛仔裤、西装、现代塑料制品；'
    '严禁近现代碎花棉衣、现代建筑、古今混搭、无关帝王宫廷；严禁写实摄影、真人照片、3D渲染、日系二次元、'
    '厚涂油画、刺眼荧光色、破败斑驳、大面积死黑、苍白无色、畸形手脚、乱码、水印、悬浮文字和UI。'
)
SPACES = (
    ('古朴堂屋', '古代木构堂屋，素袍长者与家人围坐木案，茶盏与素面屏风形成纵深'),
    ('古代集市', '古代青石街巷集市，布衣行人、竹篮、挑担小贩与无字木招牌，人物克制交谈'),
    ('田野山径', '淡墨远山前的田野与山径，古代布衣人物持传统农具歇息交谈，疏朗开阔'),
    ('松竹水榭', '苍劲老松与修竹掩映的水榭石桥，文士凭栏沉思或同行，月色与远山淡墨留白'),
    ('古朴庭院', '古代青砖小院、竹影与老井，长者与晚辈相互搭手，宽袖素袍衣纹流畅'),
    ('文士书斋', '木格窗旁的书斋，文士于木案前读素面卷轴，笔砚与叠放古籍，窗外松竹和远山'),
)


def scene_direction(text: str, index: int) -> str:
    rules = (
        (r'买菜|集市|街坊|摊位|邻居|市集', 1),
        (r'田地|农作|耕种|丰收|稻田|麦田', 2),
        (r'散步|公园|湖边|桥|漫步|晨练', 3),
        (r'院子|庭院|晾晒|井|石磨', 4),
        (r'卧室|居室|衣物|衣柜|梳头|睡前', 5),
        (r'吃饭|晚饭|家人|子女|孩子|商量|聚会', 0),
    )
    selected = next((space for pattern, space in rules if re.search(pattern, text)), None)
    if selected is None:
        # Abstract philosophy can use ordinary shared spaces without inventing
        # a specific historical event, season or harvest.
        selected = (0, 3, 4, 5)[index % 4]
    name, details = SPACES[selected]
    return (
        f'场景空间：{name}，{details}。依据本镜正文表现有意义的人物动作、手部细节和克制微表情；'
        '服饰和人物身份保持连续，避免所有镜头重复同一书斋读书动作；仅用符合古代语境的卷轴、笔砚、茶盏与竹篮。'
        f'本镜含义（只据此设计画面，不绘制这些文字）：{text}'
    )


def grid_prompt(scenes: list[str], cover: bool = False, grid_cells: int = 2, aspect: str = '4:3') -> str:
    if grid_cells not in (2, 3):
        raise ValueError('国学宫格仅支持2x2或3x3')
    cell_count = grid_cells * grid_cells
    directions = [scene_direction(text, i) for i, text in enumerate(scenes)]
    if cover and directions:
        directions[0] = ('独立封面视觉：凝聚全文哲理共鸣，古代文士或长者通过自然动作与克制神态表现主题，'
                         '前景笔砚卷轴、中景人物、后景松竹月色或古朴庭院，疏朗构图；不是正文第一个镜头的重复。'
                         + directions[0])
    while len(directions) < cell_count:
        directions.append('传统庭院与远山生活空镜，清朗自然天光，无文字、无现代物件。')
    grid_label = '四宫格' if grid_cells == 2 else '九宫格'
    return (
        f'生成一张{aspect}源图，严格{grid_cells}行{grid_cells}列{grid_label}，{cell_count}个等大格子按行从左至右对应下列镜头。'
        f'每格都是完整的{aspect}构图，人物、手部、卷轴完整保留，不生成竖图，不在图内添加模糊填充。'
        '不要分隔线、边框、间隙、编号；细节优先用于人物线条、衣料、手工布鞋和景深，不用模糊掩盖细节。'
        + BASE + '负面约束：' + NEGATIVE
        + '所有文字由后期合成：书皮、木招牌、中堂条幅一律不写字，避免乱码。'
        + '\n镜头布局（这些标签不可出现在图中）：\n'
        + '\n'.join(f'{i+1}. {value}' for i, value in enumerate(directions[:cell_count]))
        + '\n参考图只决定笔触、宣纸肌理、设色和光影：灰米纸底、浓淡墨线、松树苍劲枝干、肤色温和、灰蓝远山。'
        '每格根据分镜重新构图；不要复制参考图的人物姿态、月亮位置、书中文字或单幅构图。'
        f'超高细节，古典工笔淡墨，细腻宣纸墨韵，低饱和淡彩，松竹山水与文人生活气韵，{aspect}构图。'
    )


def single_prompt(scene: str, aspect: str = '4:3') -> str:
    return (
        f'生成一张完整的{aspect}独立画面，不要宫格、分隔线、边框或文字。'
        + BASE + '负面约束：' + NEGATIVE + scene_direction(scene, 0)
        + '参考图只决定笔触、宣纸肌理、设色和光影；依照本镜剧情重新构图，不复制参考图文字。'
    )
