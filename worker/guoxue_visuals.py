"""Traditional everyday-life gongbi direction, independent of copy rewriting."""
from __future__ import annotations

import re

STYLE_ID = 'guoxue_gongbi_life'
BASE = (
    '近现代怀旧世情·全景写实工笔风，面向55至65岁观众。中国传统工笔画结合近现代写实风俗插画，'
    '熟宣纸细腻肌理、精细流畅铁线勾勒、多层轻透分染；暖米黄纸底，藏青蓝、碎花粉橘、秋叶金黄、'
    '熟栗褐、青砖灰和菊花金黄色。清朗温和斜阳与柔和自然天光，明润通透，避免死黑和苍白褪色。'
    '人物比例自然、面容质朴慈厚，使用近现代中式传统日常服饰：斜襟大褂、碎花棉布衣裤、老布衫；'
    '人物一律穿纯素黑鞋面白布底的手工千层底布鞋或老式绣花鞋。'
    '这是传统生活智慧的视觉演绎，提到古人和经典时用读书、相处与日常实践表达，不重演古代宫廷。'
    '前景生活道具、中景人物互动、后景真实空间形成清楚纵深；每格保留顶部标题和下方三分之一字幕安全区。'
)
NEGATIVE = (
    '严禁Nike、Swoosh、Adidas、品牌Logo、商标、运动鞋、球鞋、胶底鞋、背包、双肩包、斜挎包、'
    '塑料水杯、保温杯、矿泉水瓶、现代手表、T恤、卫衣、牛仔裤、西装、现代塑料制品；'
    '严禁古代汉服大袖、高髻、宫廷帝王、古今混搭；严禁写实摄影、真人照片、3D渲染、日系二次元、'
    '厚涂油画、刺眼荧光色、破败斑驳、大面积死黑、苍白无色、畸形手脚、乱码、水印、悬浮文字和UI。'
)
SPACES = (
    ('堂屋正厅', '老式中式堂屋八仙桌与太师椅旁，以茶盏、条案瓷瓶和无字中堂画形成纵深'),
    ('集市街巷', '晨光微露的青石板蔬菜早市，竹编菜篮、挑担小贩、无字木招牌，街坊交谈'),
    ('田野田埂', '金黄开阔的田野与篱笆菜园，长辈持传统农具歇息交流，农作物形成远近层次'),
    ('林荫公园', '老树浓荫下的石子路、石拱桥与湖畔凉亭，长辈缓步同行或在石凳对谈'),
    ('农家庭院', '青砖农家小院、晾晒的棉布衣物、老井和石磨，家人整理物件或相互搭手'),
    ('老式居室', '木格窗与老木柜旁的居室，长辈整理衣物、翻阅素色无字旧书或与家人交谈'),
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
        '服饰和人物身份保持连续，避免所有镜头都在书房。仅用竹篮、蒲扇、折扇、盖碗、紫砂壶、白瓷碗等传统道具。'
        f'本镜含义（只据此设计画面，不绘制这些文字）：{text}'
    )


def grid_prompt(scenes: list[str], cover: bool = False) -> str:
    directions = [scene_direction(text, i) for i, text in enumerate(scenes)]
    if cover and directions:
        directions[0] = ('独立封面视觉：凝聚全文生活共鸣，近现代长辈与家人有真实情绪互动，'
                         '前景微虚传统道具、中景人物、后景庭院或堂屋，顶部留白；不是正文第一个镜头的重复。'
                         + directions[0])
    while len(directions) < 9:
        directions.append('传统庭院与远山生活空镜，清朗自然天光，无文字、无现代物件。')
    return (
        '生成一张2:3竖版源图，严格3行3列九宫格，9个等大格子按行从左至右对应下列镜头。'
        '每格都是完整的9:16竖版构图，主体保持中央安全区，允许少量边缘裁切。'
        '不要分隔线、边框、间隙、编号；细节优先用于人物线条、衣料、手工布鞋和景深，不用模糊掩盖细节。'
        + BASE + '负面约束：' + NEGATIVE
        + '所有文字由后期合成：书皮、木招牌、中堂条幅一律不写字，避免乱码。'
        + '\n镜头布局（这些标签不可出现在图中）：\n'
        + '\n'.join(f'{i+1}. {value}' for i, value in enumerate(directions[:9]))
        + '\n超高细节，经典中式风俗画构图，细腻宣纸墨韵，色彩明润醇厚，纪实全景生活质感。'
    )
