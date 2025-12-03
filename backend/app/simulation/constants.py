"""
双层地形架构所需的公共常量。

这些值直接来源于《GeoPhysics Engine Design v2》文档：
- 逻辑层 (CPU) 分辨率：128 x 40
- 物理层 (GPU) 分辨率：2048 x 640 (= 16 倍超采样)
- 时间尺度：基于地质年代的动态时间流 (Chronos Flow)
"""

LOGIC_RES_X = 128
LOGIC_RES_Y = 40

PHYSICS_SCALE = 16
PHYSICS_RES_X = LOGIC_RES_X * PHYSICS_SCALE  # 2048
PHYSICS_RES_Y = LOGIC_RES_Y * PHYSICS_SCALE  # 640

# ===========================
# 时间尺度定义 (Chronos Flow)
# ===========================
# 基准步长：用于计算倍率的标准（1.0x）
BASE_YEARS_PER_TURN = 500_000 

# 起始年份：28亿年前
START_YEAR = -2_800_000_000

# 时代配置表 (必须按时间顺序排列)
# end_year: 该时代结束的年份
# years_per_turn: 该时代的每回合年数
# name: 时代名称
# description: 用于Prompt的描述
#
# 设计目标：
# - 前期（太古宙+元古宙）快速跳过，约55回合到达寒武纪
# - 阶梯式减速：100万年 → 50万年 → 25万年
# - 总游戏流程约920回合
ERA_TIMELINE = [
    {
        "end_year": -2_500_000_000, 
        "name": "Archean (太古宙)", 
        "years_per_turn": 20_000_000,  # 2000万年/回合，约15回合跳过
        "description": "单细胞生命的漫长停滞期，需快速跳过",
        "evolution_guide": "时间跨度极大（2000万年/回合）。允许发生剧烈的形态改变（数值变化 ±3.0 ~ ±5.0）。允许单回合内完成重大器官演化。"
    },
    {
        "end_year": -541_000_000, 
        "name": "Proterozoic (元古宙)", 
        "years_per_turn": 50_000_000,  # 5000万年/回合，约39回合跳过
        "description": "真核生物与多细胞生物的孕育期",
        "evolution_guide": "时间跨度很大（5000万年/回合）。允许显著的形态调整（数值变化 ±2.0 ~ ±4.0）。器官演化可跨越多个阶段。"
    },
    {
        "end_year": -252_000_000, 
        "name": "Paleozoic (古生代)", 
        "years_per_turn": 1_000_000,   # 100万年/回合，约289回合 ⭐重点体验
        "description": "寒武纪大爆发！物种多样性激增，生命形式的黄金时代",
        "evolution_guide": "核心游戏体验期（100万年/回合）。这是物种多样性爆发的关键时期。允许适度的形态调整（数值变化 ±0.8 ~ ±2.0）。鼓励新器官和新物种的涌现。"
    },
    {
        "end_year": -66_000_000, 
        "name": "Mesozoic (中生代)", 
        "years_per_turn": 500_000,     # 50万年/回合，约372回合
        "description": "爬行动物的黄金时代，恐龙称霸",
        "evolution_guide": "稳定演化期（50万年/回合）。时间分辨率提高。允许中等幅度的形态调整（数值变化 ±0.5 ~ ±1.5）。重点关注体型和生态位分化。"
    },
    {
        "end_year": 0, 
        "name": "Cenozoic (新生代)", 
        "years_per_turn": 250_000,     # 25万年/回合，约264回合
        "description": "哺乳动物与鸟类的崛起",
        "evolution_guide": "精细演化期（25万年/回合）。高时间分辨率。允许精细的形态微调（数值变化 ±0.3 ~ ±1.0）。关注行为、智力与代谢的优化。"
    }
]

def get_time_config(turn_index: int) -> dict:
    """根据回合数计算当前时间配置
    
    Returns:
        {
            "current_year": int,
            "years_per_turn": int,
            "era_name": str,
            "scaling_factor": float,
            "evolution_guide": str
        }
    """
    current_year = START_YEAR
    remaining_turns = turn_index
    
    active_config = ERA_TIMELINE[-1] # 默认最后一个
    
    for config in ERA_TIMELINE:
        # 计算该时代持续多少年
        era_duration = config["end_year"] - current_year
        if era_duration <= 0:
            continue
            
        # 该时代持续多少回合
        era_turns = era_duration // config["years_per_turn"]
        
        if remaining_turns < era_turns:
            # 就在这个时代
            current_year += remaining_turns * config["years_per_turn"]
            active_config = config
            break
        else:
            # 走完这个时代
            current_year = config["end_year"]
            remaining_turns -= era_turns
            
            # 如果是最后一个时代，继续累加
            if config == ERA_TIMELINE[-1]:
                current_year += remaining_turns * config["years_per_turn"]
                active_config = config

    return {
        "current_year": current_year,
        "years_per_turn": active_config["years_per_turn"],
        "era_name": active_config["name"],
        "scaling_factor": active_config["years_per_turn"] / BASE_YEARS_PER_TURN,
        "evolution_guide": active_config["evolution_guide"]
    }

# 兼容旧代码的常量（取基准值）
TURN_DURATION_YEARS = BASE_YEARS_PER_TURN 
GEOLOGICAL_YEAR = 1000  # 1个"地质年"单位 = 1000真实年
DT = 1.0  # 每个物理步代表 1 个地质年

# 回合到物理步的转换 (使用基准值，具体物理步长需在Engine中动态调整)
PHYSICS_STEPS_PER_TURN = TURN_DURATION_YEARS // GEOLOGICAL_YEAR  # 500 步/回合

# 派生时间常量
SECONDS_PER_YEAR = 365.25 * 24 * 3600  # 31,557,600 秒
GEOLOGICAL_TIME_SCALE = GEOLOGICAL_YEAR / SECONDS_PER_YEAR  # 地质年对应的秒数比例 (≈3.17e-5)

# ===========================
# 地球物理常量
# ===========================
EARTH_RADIUS_KM = 6371.0
MAX_PLATES = 32  # 最大板块数量支持

# 板块运动相关
TYPICAL_PLATE_SPEED_M_PER_YEAR = 0.05  # 典型板块速度：5 cm/year
PLATE_ANGULAR_VEL_RAD_PER_GEO_YEAR = (
    TYPICAL_PLATE_SPEED_M_PER_YEAR / (EARTH_RADIUS_KM * 1000)
) * GEOLOGICAL_YEAR  # ≈ 7.85e-6 rad/geo_year

# 地质作用速率
MOUNTAIN_UPLIFT_M_PER_YEAR = 0.005  # 造山运动：5 mm/year (如喜马拉雅)
MOUNTAIN_UPLIFT_M_PER_GEO_YEAR = MOUNTAIN_UPLIFT_M_PER_YEAR * GEOLOGICAL_YEAR  # 5 m/geo_year

SUBDUCTION_RATE_M_PER_YEAR = 0.002  # 俯冲下沉：2 mm/year (如马里亚纳海沟)
SUBDUCTION_RATE_M_PER_GEO_YEAR = SUBDUCTION_RATE_M_PER_YEAR * GEOLOGICAL_YEAR  # 2 m/geo_year

RIFT_EXTENSION_M_PER_YEAR = 0.025  # 裂谷扩张：2.5 cm/year (如大西洋中脊)
RIFT_EXTENSION_M_PER_GEO_YEAR = RIFT_EXTENSION_M_PER_YEAR * GEOLOGICAL_YEAR  # 25 m/geo_year

# 侵蚀速率
EROSION_RATE_M_PER_YEAR = 0.001  # 水力侵蚀：1 mm/year (温带山地)
EROSION_RATE_M_PER_GEO_YEAR = EROSION_RATE_M_PER_YEAR * GEOLOGICAL_YEAR  # 1 m/geo_year

# 气候时间尺度因子（气候变化比板块运动快得多）
CLIMATE_DT_SCALE = 0.01  # 气候按 10年 为单位更新（相对于 1000年的地质年）
