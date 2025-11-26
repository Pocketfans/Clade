"""
双层地形架构所需的公共常量。

这些值直接来源于《GeoPhysics Engine Design v2》文档：
- 逻辑层 (CPU) 分辨率：128 x 40
- 物理层 (GPU) 分辨率：2048 x 640 (= 16 倍超采样)
- 时间尺度：1 turn = 50万年，物理步长基于"地质年"单位
"""

LOGIC_RES_X = 128
LOGIC_RES_Y = 40

PHYSICS_SCALE = 16
PHYSICS_RES_X = LOGIC_RES_X * PHYSICS_SCALE  # 2048
PHYSICS_RES_Y = LOGIC_RES_Y * PHYSICS_SCALE  # 640

# ===========================
# 时间尺度定义
# ===========================
TURN_DURATION_YEARS = 500_000  # 1 turn = 50万年
GEOLOGICAL_YEAR = 1000  # 1个"地质年"单位 = 1000真实年
DT = 1.0  # 每个物理步代表 1 个地质年

# 回合到物理步的转换
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
