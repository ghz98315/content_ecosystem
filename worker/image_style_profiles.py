"""隔离的图片视觉配置资产。

流程代码只消费 profile 文本；九宫格生成、源图校验和本地切图不在此模块实现。
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ImageStyleProfile:
    style_id: str
    categories: frozenset[str]
    direction: str
    positive: str
    negative: str


_COMMON_NEGATIVE = (
    "无悬浮文字、字幕、标签、字母、数字、徽标、水印、后期排版字；"
    "无畸形五官、残缺肢体、分隔线、边框、留白"
)


PROFILES: dict[str, ImageStyleProfile] = {
    "history_heroic": ImageStyleProfile(
        "history_heroic", frozenset({"social_science"}),
        "正统帝王画卷·朝代考据风",
        "9:16竖版，中国传统工笔院体画，历代帝王图卷，熟宣泛黄绢本肌理，工笔铁线勾勒，多层轻透淡彩，低饱和文人矿物色，明朗通透全景平光；以帝王、将相、士人和百姓在具体事件中的关系与行动为中心，九格场景必须有明显变化，不得全部是朝堂或宫殿。场景矩阵按文案选择：朝堂议政与宫门传诏、帝王出巡与城门迎送、山河关隘与行军列阵、战后残垣与民众安置、书院论学与案头读简、农耕水利与市井民生、工坊铸器与使者往来、江河驿路与夜行灯火；朝堂最多作为其中一至两格，其他格优先使用开放空间、道路、城郭、山水和人物行动。构图可用中轴、对角线、远景长卷、近景人物互动等多种方式，前中后景层次清楚。严格保持同一朝代的冠冕、袍服、官制、器物和建筑考据。战争只用列阵、残垣、烽烟、碎裂玉玺等象征表达，不出现血腥。",
        _COMMON_NEGATIVE + "；禁止地图、疆域轮廓、边界线、旗帜徽章、现代政治人物或现实政治场景；禁止现代服装、民国服饰、现代建筑、古今时代混搭、奇幻盔甲和大面积死黑",
    ),
    "history_ink_scroll": ImageStyleProfile(
        "history_ink_scroll", frozenset({"social_science"}),
        "工笔淡彩·古代世情风俗画",
        "9:16竖版，中国传统工笔淡彩，古典世情风俗画，熟宣纸与米黄纸底，铁线描、多层轻薄淡彩；赭石、黛青、茶褐、淡朱砂的低饱和雅致色；柔和自然天光。前景微虚茶盏、书卷、信笺等生活道具，中景普通人物的微表情、眼神与肢体互动，后景古代庭院、山水烟波；以人与人的关系张力为叙事中心，不使用帝王朝堂宏大构图。",
        _COMMON_NEGATIVE + "；禁止地图、疆域轮廓、边界线、旗帜徽章、现代政治人物或现实政治场景；禁止宫廷帝王、百官列阵、民国长衫旗袍、现代服装、现代建筑、古今时代混搭和血腥",
    ),
    "history_gongbi_cinematic": ImageStyleProfile(
        "history_gongbi_cinematic", frozenset({"social_science"}),
        "工笔淡彩·民国近代世情风俗画",
        "9:16竖版，中国传统工笔淡彩插画，明确为1910至1940年代的中国民国及近代世情风俗画，绝非古代场景。熟宣纸肌理，工笔铁线勾线，多层淡彩；米黄纸底配赭石、黛青、茶褐、淡朱砂，温和柔润自然漫反射天光。每格必须有至少两位可见人物并以互动为中心：长衫大褂、中山装、素雅立领旗袍、老布衫、齐耳短发；场景使用民国青砖洋房、木格窗、老式书房、民国木案几，搭配盖碗茶、复古眼镜和旧信封。时代统一，清雅厚重。",
        _COMMON_NEGATIVE + "；禁止地图、疆域轮廓、边界线、旗帜徽章、现代政治人物或现实政治场景；禁止无人物的静物或空庭院、古代汉服、古代高髻、古代宫殿、古代瓷器陈设、清代辫发、现代T恤卫衣、现代西装、超现代建筑和古今时代混搭",
    ),
}


def get_profile(style_id: str, category: str = "health") -> ImageStyleProfile | None:
    """只返回属于当前内容类别的 profile，防止视觉资产跨类别注入。"""
    profile = PROFILES.get(str(style_id or "").strip())
    if profile is None or category not in profile.categories:
        return None
    return profile


def historical_era_lock(text: str) -> str:
    """从场景文字提取保守的时代锁；无法确认时明确要求不要猜测。"""
    value = str(text or "")
    if re.search(r"民国|近代|中山装|旗袍|长衫|五四|租界", value):
        return "时代锁定：民国及近代；只使用民国服化道与青砖老宅/老式书房，不得出现古代汉服、高髻或现代都市建筑。"
    eras = (
        (r"秦|汉|三国|魏晋", "时代锁定：秦汉/三国/魏晋；使用对应冠冕、深衣、进贤冠与竹简，不混入后世服饰。"),
        (r"隋|唐|五代", "时代锁定：隋唐/五代；使用幞头、圆领袍、蹀躞带与品级色，不混入宋明清服饰。"),
        (r"宋", "时代锁定：两宋；使用展脚幞头、方心曲领与宋制官服，不混入明清服饰。"),
        (r"明|大明", "时代锁定：大明；使用双翅乌纱帽、官服补子与玉革带，不混入清代辫发朝珠。"),
        (r"清|大清", "时代锁定：大清；使用顶戴花翎、补服、马蹄袖与朝珠，不混入汉唐冠服。"),
    )
    for pattern, lock in eras:
        if re.search(pattern, value):
            return lock
    return "时代锁定：古代未定朝代；保持中性古代服化道，不擅自猜测具体朝代，不出现民国或现代服饰。"


def history_visual_safe(text: str) -> str:
    """将不适合直接可视化的现实政治或地图叙事转为中性人文画面。"""
    value = str(text or "")
    ancient_context = bool(re.search(
        r"秦|汉|三国|魏晋|隋|唐|五代|宋|元|明|清|王朝|朝廷|诸侯|藩镇|割据|叛乱|战乱|兵戎|古代|古时|旧朝",
        value,
        flags=re.IGNORECASE,
    ))
    if ancient_context:
        value = re.sub(
            r"(?:天下|王朝|朝代|诸侯)?(?:分裂|割据|四分五裂|内乱)|分崩离析",
            "古代朝廷失序、诸侯对峙、兵戎列阵、战场混乱与残垣意象",
            value,
            flags=re.IGNORECASE,
        )
    substitutions = (
        (r"中国国家分裂|国家分裂|中国分裂|分裂国家", "各地民众和平往来、国家和睦友好相处"),
        (r"四分五裂|分崩离析|碎裂疆域|破碎国土", "完整山水与各地民众和平往来"),
        (r"中国地图|地图|疆域(?:图|线)?|国界|边界线|领土", "无字山水与地域交流意象"),
        (r"现代中国政治|现实政治|政党|选举|领导人|政府", "社会安定与民众友好交流"),
        (r"国旗|国徽|军旗", "无标识的仪式性陈设"),
    )
    for pattern, replacement in substitutions:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value
