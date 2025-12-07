"""物种命名参考模块 - 为LLM提供随机命名灵感。

此模块通过随机组合命名元素来生成命名提示，
传递给LLM作为起名参考，增加命名多样性并节省tokens。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence


# ==================== 命名词库 ====================

# 地理起源词汇 - 虚构或真实地理意象
GEOGRAPHIC_ORIGINS = [
    # 山地/高原
    "北岭", "霜脊", "云崖", "寒峰", "雪脊", "雾峦", "玄岭", "苍山",
    "断崖", "幽峡", "石脊", "冰岭", "雷峰", "风岭", "孤峰", "远山",
    # 水域
    "赤湾", "碧潭", "玄渊", "深渊", "寒泽", "暮泊", "潮湾", "幽泉",
    "碎浪", "沧海", "冰洋", "热泉", "冷泊", "渊底", "浅滩", "激流",
    # 平原/荒野
    "玄陆", "焰原", "荒漠", "冰原", "草莽", "沙洲", "盐滩", "火土",
    "裂谷", "熔岩", "冻土", "红土", "黑土", "白垩", "灰原", "赤野",
    # 森林/植被
    "暮林", "幽谷", "苔原", "密林", "荆棘", "古森", "腐林", "雨林",
    "竹海", "枯林", "沼泽", "雾沼", "深林", "翠谷", "落叶", "常青",
    # 海岸/岛屿
    "礁岸", "珊瑚", "孤岛", "暗礁", "沙岬", "风角", "潮间", "滨海",
    # 特殊环境
    "热液", "冷泉", "硫磺", "盐晶", "冰穴", "火山", "地底", "洞窟",
]

# 形态特征词汇 - 描述生物体形态
MORPHOLOGICAL_FEATURES = [
    # 头部/口器
    "长颌", "阔口", "尖吻", "裂唇", "巨颚", "细喙", "钝头", "锐齿",
    "须口", "管吻", "扁喙", "弯嘴", "獠牙", "滤齿", "无颌", "盾头",
    # 体型/躯干
    "厚甲", "薄壳", "扁躯", "圆身", "长体", "矮身", "巨躯", "微躯",
    "纺锤", "蠕形", "球状", "片状", "管状", "盘状", "星形", "辐射",
    # 四肢/附肢
    "长鳍", "羽鳍", "刺足", "蹼足", "细足", "粗腿", "多足", "无足",
    "触手", "腕足", "桨肢", "翼手", "爪足", "吸盘", "伪足", "刚毛",
    # 尾部
    "盘尾", "叉尾", "鞭尾", "扇尾", "无尾", "长尾", "短尾", "刺尾",
    # 表皮/外壳
    "鳞甲", "裸皮", "刺背", "棘皮", "革质", "骨板", "角质", "壳体",
    "软躯", "硬壳", "透明", "半透", "绒毛", "光滑", "粗糙", "多孔",
    # 特殊结构
    "弯棘", "直刺", "环纹", "分节", "融合", "对称", "不对称", "分叉",
]

# 颜色与纹理词汇
COLOR_PATTERNS = [
    # 单色
    "赤脊", "青背", "白腹", "黑身", "金鳞", "银光", "碧体", "紫身",
    "橙腹", "褐壳", "灰皮", "铜色", "铁青", "玉白", "墨黑", "霜白",
    # 纹理/花纹
    "苍纹", "斑纹", "环带", "条纹", "点斑", "云纹", "虎纹", "豹斑",
    "网纹", "波纹", "螺纹", "迷彩", "渐变", "双色", "三色", "虹彩",
    # 光泽/质感
    "荧光", "暗哑", "珠光", "丝绒", "金属", "宝石", "磨砂", "镜面",
    "半透", "乳白", "琥珀", "翡翠", "玛瑙", "珊瑚", "象牙", "炭黑",
]

# 行为与生态习性词汇
BEHAVIORAL_TRAITS = [
    # 运动方式
    "潜沙", "钻泥", "攀岩", "滑翔", "跳跃", "漂游", "蠕行", "穴居",
    "伏底", "浮游", "疾游", "缓行", "迁徙", "定栖", "游荡", "追波",
    # 捕食行为
    "逐雾", "碎岩", "滤食", "伏击", "追猎", "围捕", "吸血", "寄生",
    "腐食", "啃木", "刮藻", "吞食", "撕咬", "毒杀", "缠绕", "钳击",
    # 防御行为
    "藏身", "伪装", "警戒", "群聚", "独居", "夜行", "昼伏", "蜷缩",
    "喷墨", "放电", "发光", "排毒", "脱壳", "断尾", "装死", "威吓",
    # 繁殖/社会行为
    "筑巢", "护卵", "群居", "孤独", "领地", "迁居", "共生", "寄主",
    "孵化", "胎生", "卵生", "分裂", "出芽", "克隆", "变态", "蜕皮",
    # 特殊习性
    "嗜热", "嗜冷", "嗜盐", "嗜酸", "嗜碱", "厌氧", "好氧", "趋光",
    "避光", "感磁", "感震", "感电", "感热", "感湿", "感压", "感流",
]

# 纪念性命名词汇 - 模拟"X氏生物"（如邓氏鱼、李氏螈）
COMMEMORATIVE_PREFIXES = [
    # 真实姓氏风格（模拟发现者命名）
    "邓", "李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗", "梁",
    # 古风/神话姓氏
    "云", "风", "雷", "霜", "雪", "冰", "火", "水", "木", "金", "土",
    "龙", "凤", "虎", "鹤", "鹏", "麟", "玄", "青", "白", "朱", "墨",
    # 方位/自然姓氏
    "东", "西", "南", "北", "中", "上", "下", "远", "近", "深", "浅",
    "炎", "寒", "暗", "明", "清", "浊", "静", "动", "生", "灭", "始", "终",
]

# 地名词汇 - 用于"地名+类群"风格（如澄江虫、热河鸟）
PLACE_NAMES = [
    # 中国古生物化石产地
    "澄江", "热河", "辽西", "关岭", "贵州", "云南", "四川", "山东",
    "甘肃", "新疆", "西藏", "蒙古", "华南", "华北", "东北", "西南",
    # 虚构/意象地名
    "玄武", "青龙", "白虎", "朱雀", "蓬莱", "昆仑", "瀛洲", "方丈",
    "九州", "中原", "江南", "塞北", "岭南", "关外", "海东", "天山",
    # 地质/环境地名
    "寒武", "奥陶", "志留", "泥盆", "石炭", "二叠", "三叠", "侏罗",
    "白垩", "古近", "新近", "第四", "冰川", "火山", "深海", "浅海",
]

# 群体/谱系后缀词汇
TAXONOMIC_SUFFIXES = [
    # 动物类群
    "鱼", "虫", "兽", "螈", "蜥", "蟹", "贝", "龙", "鳗", "鸟", "蛾",
    "蚓", "蛇", "蛙", "龟", "虾", "蚌", "螺", "藻", "菌", "虱", "蚤",
    "蜗", "蝎", "蜘", "蛛", "蝇", "蚊", "蝶", "蜂", "蚁", "蝉", "蚕",
    # 形态后缀
    "形", "状", "类", "体", "质", "属", "种", "型", "系", "目", "科",
    # 特殊后缀
    "精", "灵", "魂", "怪", "妖", "仙", "神", "王", "帝", "后", "母",
]

# 拉丁学名词根（可选，供高级用法）
LATIN_ROOTS = {
    "geographic": [
        "borealis", "australis", "orientalis", "occidentalis",  # 方位
        "montanus", "lacustris", "fluvialis", "marinus",  # 环境
        "abyssalis", "pelagicus", "littoralis", "insularis",  # 海洋
        "glacialis", "thermalis", "tropicus", "arcticus",  # 气候
    ],
    "morphology": [
        "longus", "brevis", "magnus", "parvus",  # 大小
        "spinosus", "cornuta", "pinnatus", "squamosus",  # 结构
        "crassus", "gracilis", "rotundus", "planus",  # 形状
        "barbatus", "cristatus", "carinatus", "alatus",  # 特征
    ],
    "color": [
        "ruber", "niger", "albus", "viridis",  # 基本色
        "aureus", "argenteus", "caeruleus", "flavus",  # 金属/亮色
        "maculatus", "striatus", "variegatus", "unicolor",  # 花纹
    ],
    "behavior": [
        "velox", "tardus", "nocturnus", "diurnus",  # 活动
        "vorax", "placidus", "ferox", "timidus",  # 性格
        "natans", "volans", "reptans", "fossoria",  # 运动
        "migratorius", "sedentarius", "gregarius", "solitarius",  # 社会
    ],
}


# ==================== 命名风格定义 ====================

# 预设命名风格 - 每种风格有不同的命名模式和权重
NAMING_STYLES = {
    "geographic_morphology": {
        "name": "地理+形态风格",
        "description": "以栖息地意象开头，加上形态或行为特征，最后加类群后缀",
        "pattern": "[地理意象] + [形态/行为] + [类群后缀]",
        "examples": ["霜脊长鳍鱼", "玄渊盲螈", "焰原厚甲蜥", "碧潭钻泥蟹"],
        "weight": 40,  # 40% 概率
    },
    "commemorative": {
        "name": "纪念性命名风格",
        "description": "以人名/姓氏开头，加'氏'，再加类群名，模拟发现者命名",
        "pattern": "[姓氏] + 氏 + [类群]",
        "examples": ["邓氏鱼", "李氏螈", "周氏虫", "王氏龙"],
        "weight": 15,  # 15% 概率
    },
    "place_based": {
        "name": "地名+类群风格",
        "description": "以真实或虚构地名开头，直接加类群名，模拟化石产地命名",
        "pattern": "[地名] + [类群]",
        "examples": ["澄江虫", "热河鸟", "辽西龙", "关岭鱼"],
        "weight": 15,  # 15% 概率
    },
    "feature_direct": {
        "name": "特征直译风格",
        "description": "直接描述最显著的形态特征",
        "pattern": "[数量/形态词] + [特征] + [类群]",
        "examples": ["三叶虫", "盾皮鱼", "棘皮兽", "双壳贝"],
        "weight": 15,  # 15% 概率
    },
    "behavior_based": {
        "name": "行为习性风格",
        "description": "以独特的行为或生态习性命名",
        "pattern": "[行为/习性] + [类群]",
        "examples": ["伏击蟹", "滤食贝", "穴居蛇", "夜行蛾"],
        "weight": 10,  # 10% 概率
    },
    "poetic": {
        "name": "诗意/神话风格",
        "description": "带有神话色彩或诗意的命名",
        "pattern": "[神话/诗意词] + [类群/形态]",
        "examples": ["玄武龟", "朱雀鸟", "蓬莱仙螺", "昆仑雪蛾"],
        "weight": 5,  # 5% 概率
    },
}


# ==================== 命名提示生成器 ====================

@dataclass
class NamingHint:
    """命名提示数据类"""
    category: str  # 提示类别
    chinese: str   # 中文词汇
    latin: str | None = None  # 可选的拉丁词根


class NamingHintGenerator:
    """命名提示生成器 - 为LLM提供随机命名参考"""
    
    def __init__(self, seed: int | None = None):
        """
        初始化生成器
        
        Args:
            seed: 随机种子（可选，用于可复现性）
        """
        self.rng = random.Random(seed)
    
    def set_seed(self, seed: int) -> None:
        """设置随机种子"""
        self.rng = random.Random(seed)
    
    def _sample(self, pool: Sequence[str], n: int = 1) -> list[str]:
        """从词库中随机抽样"""
        n = min(n, len(pool))
        return self.rng.sample(list(pool), n)
    
    def get_geographic_hints(self, n: int = 3) -> list[str]:
        """获取地理起源词汇"""
        return self._sample(GEOGRAPHIC_ORIGINS, n)
    
    def get_morphology_hints(self, n: int = 3) -> list[str]:
        """获取形态特征词汇"""
        return self._sample(MORPHOLOGICAL_FEATURES, n)
    
    def get_color_hints(self, n: int = 2) -> list[str]:
        """获取颜色与纹理词汇"""
        return self._sample(COLOR_PATTERNS, n)
    
    def get_behavior_hints(self, n: int = 3) -> list[str]:
        """获取行为习性词汇"""
        return self._sample(BEHAVIORAL_TRAITS, n)
    
    def get_commemorative_hints(self, n: int = 2) -> list[str]:
        """获取纪念性命名词汇"""
        prefixes = self._sample(COMMEMORATIVE_PREFIXES, n)
        return [f"{p}氏" for p in prefixes]
    
    def get_suffix_hints(self, n: int = 3) -> list[str]:
        """获取类群后缀词汇"""
        return self._sample(TAXONOMIC_SUFFIXES, n)
    
    def get_place_hints(self, n: int = 2) -> list[str]:
        """获取地名词汇"""
        return self._sample(PLACE_NAMES, n)
    
    def select_naming_style(self) -> tuple[str, dict]:
        """
        根据权重随机选择一种命名风格
        
        Returns:
            (风格ID, 风格配置字典)
        """
        styles = list(NAMING_STYLES.items())
        weights = [s[1]["weight"] for s in styles]
        total = sum(weights)
        
        r = self.rng.random() * total
        cumulative = 0
        for style_id, style_config in styles:
            cumulative += style_config["weight"]
            if r <= cumulative:
                return style_id, style_config
        
        # 默认返回第一个
        return styles[0]
    
    def generate_style_hint(self) -> str:
        """
        生成包含随机命名风格的提示
        
        Returns:
            命名风格提示文本
        """
        style_id, style = self.select_naming_style()
        
        lines = [f"【本次推荐命名风格：{style['name']}】"]
        lines.append(f"说明：{style['description']}")
        lines.append(f"格式：{style['pattern']}")
        lines.append(f"示例：{', '.join(style['examples'])}")
        
        # 根据风格提供相应的词汇
        lines.append("")
        if style_id == "commemorative":
            surnames = self._sample(COMMEMORATIVE_PREFIXES, 3)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 3)  # 只取动物类群
            lines.append(f"可用姓氏：{', '.join(surnames)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
            lines.append("组合方式：[姓氏]+氏+[类群]，如'邓氏鱼'")
        elif style_id == "place_based":
            places = self.get_place_hints(4)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 3)
            lines.append(f"可用地名：{', '.join(places)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
            lines.append("组合方式：[地名]+[类群]，如'澄江虫'")
        elif style_id == "feature_direct":
            morphs = self.get_morphology_hints(4)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 3)
            lines.append(f"可用特征：{', '.join(morphs)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
            lines.append("组合方式：[特征]+[类群]，如'盾皮鱼'、'三叶虫'")
        elif style_id == "behavior_based":
            behavs = self.get_behavior_hints(4)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 3)
            lines.append(f"可用习性：{', '.join(behavs)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
            lines.append("组合方式：[习性]+[类群]，如'伏击蟹'")
        elif style_id == "poetic":
            places = self._sample(PLACE_NAMES[16:24], 3)  # 神话地名
            suffixes = self._sample(TAXONOMIC_SUFFIXES, 3)
            lines.append(f"可用意象：{', '.join(places)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
        else:  # geographic_morphology（默认）
            geos = self.get_geographic_hints(3)
            morphs = self.get_morphology_hints(3)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 3)
            lines.append(f"可用地理：{', '.join(geos)}")
            lines.append(f"可用形态：{', '.join(morphs)}")
            lines.append(f"可用类群：{', '.join(suffixes)}")
        
        return "\n".join(lines)
    
    def get_latin_hints(self, category: str | None = None, n: int = 2) -> list[str]:
        """获取拉丁词根提示"""
        if category and category in LATIN_ROOTS:
            return self._sample(LATIN_ROOTS[category], n)
        # 混合抽样
        all_roots = []
        for roots in LATIN_ROOTS.values():
            all_roots.extend(roots)
        return self._sample(all_roots, n)
    
    def generate_naming_prompt(
        self,
        include_geographic: bool = True,
        include_morphology: bool = True,
        include_color: bool = True,
        include_behavior: bool = True,
        include_commemorative: bool = True,
        include_suffix: bool = True,
        include_latin: bool = True,
        samples_per_category: int = 3,
    ) -> str:
        """
        生成完整的命名提示文本（包含随机风格指示）
        
        Args:
            include_*: 是否包含各类别
            samples_per_category: 每个类别的样本数
            
        Returns:
            格式化的命名提示文本，可直接嵌入到LLM prompt中
        """
        # 首先选择一种命名风格
        style_id, style = self.select_naming_style()
        
        lines = [f"【本次推荐命名风格：{style['name']}】"]
        lines.append(f"格式：{style['pattern']}")
        lines.append(f"示例：{', '.join(style['examples'])}")
        lines.append("")
        lines.append("【可用词汇素材】")
        
        if include_geographic:
            hints = self.get_geographic_hints(samples_per_category)
            lines.append(f"- 地理意象：{', '.join(hints)}")
        
        if include_morphology:
            hints = self.get_morphology_hints(samples_per_category)
            lines.append(f"- 形态特征：{', '.join(hints)}")
        
        if include_color:
            hints = self.get_color_hints(samples_per_category)
            lines.append(f"- 颜色纹理：{', '.join(hints)}")
        
        if include_behavior:
            hints = self.get_behavior_hints(samples_per_category)
            lines.append(f"- 行为习性：{', '.join(hints)}")
        
        if include_commemorative:
            surnames = self._sample(COMMEMORATIVE_PREFIXES, samples_per_category)
            lines.append(f"- 纪念姓氏：{', '.join(surnames)}（可加'氏'）")
        
        # 添加地名词汇
        places = self.get_place_hints(samples_per_category)
        lines.append(f"- 地名：{', '.join(places)}")
        
        if include_suffix:
            hints = self.get_suffix_hints(samples_per_category)
            lines.append(f"- 类群后缀：{', '.join(hints)}")
        
        if include_latin:
            hints = self.get_latin_hints(n=samples_per_category)
            lines.append(f"- 拉丁词根：{', '.join(hints)}")
        
        lines.append("")
        lines.append(f"⚠️ 请优先使用【{style['name']}】风格命名！")
        
        return "\n".join(lines)
    
    def generate_compact_hint(self, seed: int | None = None) -> str:
        """
        生成紧凑版命名提示（节省tokens），包含随机风格指示
        
        Args:
            seed: 可选的随机种子
            
        Returns:
            简短的命名提示，包含风格建议
        """
        if seed is not None:
            self.set_seed(seed)
        
        # 随机选择命名风格
        style_id, style = self.select_naming_style()
        
        lines = [f"【命名风格：{style['name']}】{style['pattern']}"]
        lines.append(f"示例：{', '.join(style['examples'][:2])}")
        
        # 根据风格提供简化的词汇
        if style_id == "commemorative":
            surnames = self._sample(COMMEMORATIVE_PREFIXES, 2)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 2)
            lines.append(f"本次词汇：姓氏({', '.join(surnames)}) + 氏 + 类群({', '.join(suffixes)})")
        elif style_id == "place_based":
            places = self.get_place_hints(2)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 2)
            lines.append(f"本次词汇：地名({', '.join(places)}) + 类群({', '.join(suffixes)})")
        elif style_id == "feature_direct":
            morphs = self.get_morphology_hints(2)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 2)
            lines.append(f"本次词汇：特征({', '.join(morphs)}) + 类群({', '.join(suffixes)})")
        elif style_id == "behavior_based":
            behavs = self.get_behavior_hints(2)
            suffixes = self._sample(TAXONOMIC_SUFFIXES[:12], 2)
            lines.append(f"本次词汇：习性({', '.join(behavs)}) + 类群({', '.join(suffixes)})")
        elif style_id == "poetic":
            places = self._sample(PLACE_NAMES[16:24], 2)
            suffixes = self._sample(TAXONOMIC_SUFFIXES, 2)
            lines.append(f"本次词汇：意象({', '.join(places)}) + 类群({', '.join(suffixes)})")
        else:  # geographic_morphology
            geo = self._sample(GEOGRAPHIC_ORIGINS, 2)
            morph = self._sample(MORPHOLOGICAL_FEATURES, 2)
            suffix = self._sample(TAXONOMIC_SUFFIXES[:12], 2)
            lines.append(f"本次词汇：地理({', '.join(geo)}) + 形态({', '.join(morph)}) + 类群({', '.join(suffix)})")
        
        return "\n".join(lines)
    
    def generate_habitat_specific_hint(self, habitat_type: str) -> str:
        """
        根据栖息地类型生成针对性的命名提示
        
        Args:
            habitat_type: 栖息地类型
            
        Returns:
            针对性的命名提示
        """
        # 根据栖息地筛选相关词汇
        habitat_geo_map = {
            "marine": ["碧潭", "沧海", "潮湾", "浅滩", "珊瑚", "暗礁", "深渊"],
            "deep_sea": ["玄渊", "深渊", "热液", "冷泉", "渊底", "黑潮", "幽暗"],
            "coastal": ["礁岸", "潮间", "滨海", "沙岬", "风角", "浪花", "盐滩"],
            "freshwater": ["碧潭", "寒泽", "激流", "浅滩", "幽泉", "冰泊", "暮泊"],
            "amphibious": ["雾沼", "沼泽", "潮间", "湿地", "泥滩", "苔原"],
            "terrestrial": ["焰原", "荒漠", "冰原", "草莽", "幽谷", "暮林", "苍山"],
            "aerial": ["云崖", "风岭", "霜脊", "孤峰", "远山", "雾峦", "晴空"],
        }
        
        habitat_behav_map = {
            "marine": ["漂游", "疾游", "滤食", "追波", "浮游"],
            "deep_sea": ["伏底", "发光", "感压", "嗜热", "厌氧"],
            "coastal": ["潜沙", "伏击", "潮汐", "挖掘", "攀岩"],
            "freshwater": ["逆流", "底栖", "啃藻", "筑巢", "穴居"],
            "amphibious": ["两栖", "蜕皮", "变态", "钻泥", "伪装"],
            "terrestrial": ["攀岩", "穴居", "奔跑", "跳跃", "滑翔"],
            "aerial": ["滑翔", "翱翔", "俯冲", "迁徙", "筑巢"],
        }
        
        geo_pool = habitat_geo_map.get(habitat_type, GEOGRAPHIC_ORIGINS[:10])
        behav_pool = habitat_behav_map.get(habitat_type, BEHAVIORAL_TRAITS[:10])
        
        geo = self._sample(geo_pool, 2)
        morph = self._sample(MORPHOLOGICAL_FEATURES, 2)
        behav = self._sample(behav_pool, 2)
        suffix = self._sample(TAXONOMIC_SUFFIXES, 2)
        
        return (
            f"【{habitat_type}栖息地命名参考】\n"
            f"- 地理：{', '.join(geo)}\n"
            f"- 形态：{', '.join(morph)}\n"
            f"- 习性：{', '.join(behav)}\n"
            f"- 后缀：{', '.join(suffix)}"
        )


# ==================== 便捷函数 ====================

# 全局生成器实例
_default_generator = NamingHintGenerator()


def get_naming_hint(seed: int | None = None) -> str:
    """获取命名提示（便捷函数）"""
    if seed is not None:
        _default_generator.set_seed(seed)
    return _default_generator.generate_naming_prompt()


def get_compact_naming_hint(seed: int | None = None) -> str:
    """获取紧凑版命名提示（便捷函数）"""
    return _default_generator.generate_compact_hint(seed)


def get_habitat_naming_hint(habitat_type: str, seed: int | None = None) -> str:
    """获取栖息地特定命名提示（便捷函数）"""
    if seed is not None:
        _default_generator.set_seed(seed)
    return _default_generator.generate_habitat_specific_hint(habitat_type)
