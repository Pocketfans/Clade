"""板块构造系统配置常量"""

TECTONIC_CONFIG = {
    # ==================== 时间尺度 ====================
    "turns_per_million_years": 2,  # 每200万年1回合
    
    # ==================== 板块生成 ====================
    "plate_generation": {
        "num_major_plates": (2, 4),      # 主要板块数量范围
        "num_medium_plates": (4, 8),     # 中型板块数量范围
        "num_minor_plates": (6, 15),     # 小板块数量范围
        
        "major_size_ratio": (0.10, 0.25),   # 大板块占总面积比例
        "medium_size_ratio": (0.02, 0.08),  # 中板块占总面积比例
        "minor_size_ratio": (0.005, 0.02),  # 小板块占总面积比例
        
        "continental_ratio": 0.4,         # 大陆板块比例
        "boundary_noise_strength": 0.3,   # 边界噪声强度
        "min_plate_seed_distance": 5,     # 板块种子点最小间距
    },
    
    # ==================== 板块运动 ====================
    "motion": {
        "base_velocity": 0.1,           # 基础速度 (格/回合)
        "max_velocity": 0.3,            # 最大速度
        "min_velocity": 0.01,           # 最小速度
        "velocity_decay": 0.98,         # 每回合速度衰减
        "angular_velocity_range": (-0.02, 0.02),  # 角速度范围 (rad/回合)
        
        # 纬度效应
        "polar_motion_damping": 0.5,    # 极地运动阻尼
        "tropical_motion_boost": 1.1,   # 热带运动加速
        
        # Y轴运动限制
        "max_y_velocity": 0.15,         # 最大Y轴速度
        "polar_bounce_factor": 0.3,     # 极地反弹系数
    },
    
    # ==================== 地形变化 ====================
    # 渐进式变化：每回合约50万年，变化应该非常缓慢
    # 真实地球：喜马拉雅山每年隆起约1cm = 5000年/回合 * 0.01m = 50m/回合（太快）
    # 游戏平衡：进一步降低，让变化几乎不可见
    "terrain": {
        "max_elevation_change": 0.5,    # 单回合最大海拔变化 (米) - 极度缓慢
        "erosion_rate": 0.02,           # 侵蚀速率 (米/回合) - 极慢
        "mountain_growth_rate": 0.3,    # 造山速率 (米/回合) - 极慢
        "subduction_depth_rate": 0.2,   # 俯冲深度增加速率 (米/回合) - 极慢
        "rift_subsidence_rate": 0.15,   # 裂谷下沉速率 (米/回合) - 极慢
        
        # 边界影响范围
        "boundary_effect_radius": 8,    # 边界效应影响半径 (格) - 更大范围平滑过渡
        
        # 平滑参数
        "smoothing_iterations": 3,      # 每回合平滑迭代次数 - 增加
        "smoothing_strength": 0.25,     # 平滑强度 (0-1) - 增强
        
        # 温度联动
        "temp_per_100m_elevation": -0.6,  # 每100米海拔温度变化 (°C)
    },
    
    # ==================== 地质特征 ====================
    "features": {
        # 火山
        "volcano_subduction_probability": 0.8,  # 俯冲带火山概率
        "volcano_hotspot_probability": 0.95,    # 热点火山概率
        "volcano_rift_probability": 0.4,        # 裂谷火山概率
        "volcano_min_distance": 3,              # 火山最小间距
        
        # 热点
        "num_hotspots": (3, 6),                 # 热点数量范围
        "hotspot_min_distance": 15,             # 热点最小间距
        
        # 海沟 - 渐进式加深，不是直接设为最深
        "trench_max_depth": -8000,              # 海沟最大深度 (米)
        "trench_deepen_rate": 50,               # 海沟每回合加深速率 (米)
        "trench_min_ocean_depth": -500,         # 形成海沟的最小海洋深度
        
        # 构造湖泊
        "rift_lake_probability": 0.15,          # 裂谷地带形成湖泊的概率
        "rift_lake_min_distance": 8,            # 裂谷湖最小间距
        "crater_lake_probability": 0.3,         # 火山口形成湖泊的概率
    },
    
    # ==================== 事件概率 ====================
    "events": {
        "earthquake_base_prob": 0.1,    # 基础地震概率
        "volcano_eruption_base_prob": 0.05,  # 基础火山喷发概率
        
        # 边界类型对事件的影响
        "boundary_earthquake_boost": {
            "divergent": 1.5,
            "convergent": 3.0,
            "subduction": 4.0,
            "transform": 2.5,
        },
        "boundary_volcano_boost": {
            "divergent": 2.0,
            "convergent": 1.5,
            "subduction": 5.0,
            "transform": 0.5,
        },
    },
    
    # ==================== 压力影响 ====================
    "pressure_effects": {
        "orogeny": {
            "collision_speed_boost": 1.5,
            "elevation_change_boost": 2.0,
        },
        "volcanic_eruption": {
            "eruption_probability_boost": 3.0,
            "magma_upwelling": 0.5,
        },
        "earthquake_period": {
            "all_speed_boost": 1.2,
            "earthquake_probability_boost": 2.0,
        },
        "rifting": {
            "divergent_speed_boost": 1.8,
            "new_rift_chance": 0.3,
        },
        "glacial_period": {
            "all_speed_damping": 0.8,
        },
    },
}

# 边界类型常量
BOUNDARY_TYPE_CODES = {
    "internal": 0,
    "divergent": 1,
    "convergent": 2,
    "subduction": 3,
    "transform": 4,
}

# 板块类型密度
PLATE_DENSITIES = {
    "continental": 2.7,  # 大陆板块密度 (g/cm³)
    "oceanic": 3.0,      # 洋壳密度
    "mixed": 2.85,       # 混合板块
}

