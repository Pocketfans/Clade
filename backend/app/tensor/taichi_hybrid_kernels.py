"""
Taichi 内核定义模块

此模块在导入时初始化 Taichi 并定义所有内核。
支持多种 GPU 后端：
- NVIDIA: CUDA (首选)
- AMD: Vulkan
- Intel: Vulkan
- Apple: Metal (macOS)

如果 Taichi 不可用，则此模块的导入会失败。
"""

import logging
import taichi as ti

logger = logging.getLogger(__name__)

# 初始化 Taichi（在模块级别，但只初始化一次）
_taichi_initialized = False
_taichi_backend = None

def _ensure_taichi_init():
    """确保 Taichi 只初始化一次，支持多 GPU 厂商
    
    尝试顺序：
    1. CUDA (NVIDIA 最优)
    2. Vulkan (AMD/Intel/NVIDIA 通用)
    3. Metal (macOS)
    4. OpenGL (兼容层)
    5. CPU (最后回退)
    """
    global _taichi_initialized, _taichi_backend
    
    if _taichi_initialized:
        return _taichi_backend
    
    # 按优先级尝试各后端
    backends = [
        ("cuda", ti.cuda, "NVIDIA CUDA"),
        ("vulkan", ti.vulkan, "Vulkan (AMD/Intel/NVIDIA)"),
        ("metal", ti.metal, "Apple Metal"),
        ("opengl", ti.opengl, "OpenGL"),
    ]
    
    for backend_name, backend_arch, backend_desc in backends:
        try:
            ti.init(
                arch=backend_arch, 
                default_fp=ti.f32, 
                offline_cache=True,
                # 对于 Vulkan，设置更宽松的内存限制
                device_memory_fraction=0.7 if backend_name == "vulkan" else 0.8,
            )
            _taichi_initialized = True
            _taichi_backend = backend_name
            logger.info(f"[Taichi] 初始化成功: {backend_desc}")
            return backend_name
        except Exception as e:
            logger.debug(f"[Taichi] {backend_desc} 初始化失败: {e}")
            continue
    
    # 所有 GPU 后端失败，抛出错误（GPU-only 模式）
    _taichi_initialized = True  # 防止重复尝试
    _taichi_backend = None
    raise RuntimeError(
        "Taichi GPU 初始化失败。支持的 GPU:\n"
        "  - NVIDIA: 需要 CUDA 驱动\n"
        "  - AMD: 需要 Vulkan 驱动 (AMD Software/ROCm)\n"
        "  - Intel: 需要 Vulkan 驱动 (Intel Graphics Driver)\n"
        "请确保已安装对应的 GPU 驱动程序。"
    )

def get_taichi_backend() -> str | None:
    """获取当前 Taichi 后端名称"""
    return _taichi_backend

_ensure_taichi_init()


@ti.kernel
def kernel_mortality(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    params: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    temp_idx: ti.i32,
    temp_opt: ti.f32,
    temp_tol: ti.f32,
):
    """死亡率计算 - Taichi 并行"""
    for s, i, j in ti.ndrange(pop.shape[0], pop.shape[1], pop.shape[2]):
        if pop[s, i, j] > 0:
            temp = env[temp_idx, i, j]
            deviation = ti.abs(temp - temp_opt)
            mortality = 1.0 - ti.exp(-deviation / temp_tol)
            result[s, i, j] = ti.max(0.01, ti.min(0.99, mortality))
        else:
            result[s, i, j] = 0.0


@ti.kernel
def kernel_diffusion(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    rate: ti.f32,
):
    """种群扩散 - Taichi 并行"""
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    neighbor_rate = rate / 4.0
    
    for s, i, j in ti.ndrange(S, H, W):
        center = pop[s, i, j] * (1.0 - rate)
        received = 0.0
        
        if i > 0:
            received += pop[s, i - 1, j] * neighbor_rate
        if i < H - 1:
            received += pop[s, i + 1, j] * neighbor_rate
        if j > 0:
            received += pop[s, i, j - 1] * neighbor_rate
        if j < W - 1:
            received += pop[s, i, j + 1] * neighbor_rate
        
        new_pop[s, i, j] = center + received


@ti.kernel
def kernel_apply_mortality(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    mortality: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """应用死亡率 - Taichi 并行"""
    for s, i, j in ti.ndrange(pop.shape[0], pop.shape[1], pop.shape[2]):
        result[s, i, j] = pop[s, i, j] * (1.0 - mortality[s, i, j])


@ti.kernel
def kernel_reproduction(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    fitness: ti.types.ndarray(dtype=ti.f32, ndim=3),
    capacity: ti.types.ndarray(dtype=ti.f32, ndim=2),
    birth_rate: ti.f32,
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """繁殖计算 - Taichi 并行
    
    【v2.2 修复】添加低宜居度繁殖抑制：
    - 宜居度低于0.20时，繁殖率大幅降低
    - 宜居度低于0.10时，几乎不繁殖
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    # 繁殖的宜居度阈值
    REPRO_MIN_SUIT = 0.10      # 低于此值几乎不繁殖
    REPRO_LOW_SUIT = 0.25      # 低于此值繁殖受抑制
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] > 0:
            total_pop = 0.0
            for sp in range(S):
                total_pop += pop[sp, i, j]
            
            cap = capacity[i, j]
            suit = fitness[s, i, j]  # fitness 即 suitability
            
            if cap > 0 and total_pop > 0:
                crowding = ti.min(1.0, total_pop / cap)
                
                # 【新增】宜居度繁殖调节因子
                suit_factor = 1.0
                if suit < REPRO_MIN_SUIT:
                    # 极低宜居度：几乎不繁殖
                    suit_factor = 0.05
                elif suit < REPRO_LOW_SUIT:
                    # 低宜居度：繁殖率线性降低
                    # 从 0.10 到 0.25，因子从 0.05 升到 0.70
                    suit_factor = 0.05 + (suit - REPRO_MIN_SUIT) / (REPRO_LOW_SUIT - REPRO_MIN_SUIT) * 0.65
                else:
                    # 正常宜居度：使用 suitability 作为系数
                    suit_factor = ti.min(1.0, suit * 1.2)
                
                effective_rate = birth_rate * suit_factor * (1.0 - crowding)
                result[s, i, j] = pop[s, i, j] * (1.0 + effective_rate)
            else:
                result[s, i, j] = pop[s, i, j]
        else:
            result[s, i, j] = 0.0


@ti.kernel
def kernel_competition(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    fitness: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    strength: ti.f32,
):
    """种间竞争 - Taichi 并行"""
    S = pop.shape[0]
    for s, i, j in ti.ndrange(pop.shape[0], pop.shape[1], pop.shape[2]):
        if pop[s, i, j] > 0:
            total_competitor = 0.0
            for sp in range(S):
                if sp != s:
                    total_competitor += pop[sp, i, j]
            
            my_fitness = fitness[s, i, j]
            if my_fitness > 0:
                pressure = total_competitor * strength / (my_fitness + 0.1)
                loss = ti.min(0.5, pressure / (pop[s, i, j] + 1.0))
                result[s, i, j] = pop[s, i, j] * (1.0 - loss)
            else:
                result[s, i, j] = pop[s, i, j] * 0.9
        else:
            result[s, i, j] = 0.0


@ti.kernel
def kernel_redistribute_population(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    current_totals: ti.types.ndarray(dtype=ti.f32, ndim=1),
    new_totals: ti.types.ndarray(dtype=ti.f32, ndim=1),
    out_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    tile_count: ti.i32,
):
    """按权重分配新的种群总数 - Taichi 并行
    
    【v2.1修复】当物种没有现有分布时，保持原样（不再均匀分配到全世界）
    这防止了新物种被错误地分配到所有地块
    """
    for s, i, j in ti.ndrange(pop.shape[0], pop.shape[1], pop.shape[2]):
        target = new_totals[s]
        if target <= 0:
            out_pop[s, i, j] = 0.0
        else:
            total = current_totals[s]
            if total > 0:
                # 按原有分布权重分配
                weight = pop[s, i, j] / total
                out_pop[s, i, j] = weight * target
            else:
                # 【v2.1修复】没有现有分布时，保持为0
                # 不再均匀分配到所有地块，防止全球扩散
                out_pop[s, i, j] = 0.0


# ============================================================================
# 迁徙相关内核 - GPU 加速物种迁徙计算
# ============================================================================

@ti.kernel
def kernel_compute_suitability(
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_prefs: ti.types.ndarray(dtype=ti.f32, ndim=2),
    habitat_mask: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """批量计算所有物种对所有地块的适宜度 - Taichi 并行
    
    Args:
        env: 环境张量 (C, H, W) - [温度, 湿度, 海拔, 资源, 陆地, 海洋, 海岸]
        species_prefs: 物种偏好 (S, 7) - [温度偏好, 湿度偏好, 海拔偏好, 资源需求, 陆地, 海洋, 海岸]
        habitat_mask: 栖息地类型掩码 (S, H, W) - 当前物种是否可以存活于该地块
        result: 适宜度输出 (S, H, W)
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        # 温度匹配 (env[0] 是归一化温度 [-1, 1], prefs[0] 是温度偏好)
        temp_diff = ti.abs(env[0, i, j] - species_prefs[s, 0])
        temp_match = ti.max(0.0, 1.0 - temp_diff * 2.0)
        
        # 湿度匹配
        humidity_diff = ti.abs(env[1, i, j] - species_prefs[s, 1])
        humidity_match = ti.max(0.0, 1.0 - humidity_diff * 2.0)
        
        # 资源匹配
        resource_match = env[3, i, j]
        
        # 栖息地类型匹配
        habitat_match = (
            env[4, i, j] * species_prefs[s, 4] +  # 陆地
            env[5, i, j] * species_prefs[s, 5] +  # 海洋
            env[6, i, j] * species_prefs[s, 6]    # 海岸
        )
        
        # 综合适宜度
        base_score = (
            temp_match * 0.3 +
            humidity_match * 0.2 +
            resource_match * 0.2 +
            habitat_match * 0.3
        )
        
        # 应用栖息地掩码（硬约束）
        if habitat_mask[s, i, j] > 0.5:
            # 如果温度或栖息地完全不匹配，适宜度归零
            if temp_match < 0.05 or habitat_match < 0.01:
                result[s, i, j] = 0.0
            else:
                result[s, i, j] = ti.max(0.0, ti.min(1.0, base_score))
        else:
            result[s, i, j] = 0.0


@ti.kernel
def kernel_compute_trait_suitability(
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """精确特质-环境匹配的宜居度计算 - Taichi GPU 并行
    
    【核心改进】每个特质都有对应的环境参数，形成精确匹配
    
    Args:
        env: 环境张量 (C, H, W) - [温度, 湿度, 海拔, 资源, 陆地, 海洋, 海岸...]
        species_traits: 物种特质 (S, 14)
            [0] 耐热性 1-10
            [1] 耐寒性 1-10
            [2] 耐旱性 1-10
            [3] 耐盐性 1-10
            [4] 光照需求 1-10
            [5] 繁殖速度 1-10
            [6] 体型 1-10
            [7] 机动性 1-10
            [8] 陆地偏好 0-1
            [9] 海洋偏好 0-1
            [10] 海岸偏好 0-1
            [11] 营养级 1-5
            [12] 年龄 0+
            [13] 专化度 0-1
        result: 适宜度输出 (S, H, W)
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    C = env.shape[0]
    
    for s, i, j in ti.ndrange(S, H, W):
        # 获取物种特质
        heat_res = species_traits[s, 0]      # 耐热性 1-10
        cold_res = species_traits[s, 1]      # 耐寒性 1-10
        drought_res = species_traits[s, 2]   # 耐旱性 1-10
        salt_res = species_traits[s, 3]      # 耐盐性 1-10
        light_req = species_traits[s, 4]     # 光照需求 1-10
        land_pref = species_traits[s, 8]     # 陆地偏好 0-1
        ocean_pref = species_traits[s, 9]    # 海洋偏好 0-1
        coast_pref = species_traits[s, 10]   # 海岸偏好 0-1
        specialization = species_traits[s, 13]  # 专化度 0-1
        
        # 获取环境参数（假设 env 通道顺序）
        tile_temp = env[0, i, j]         # 归一化温度 [-1, 1] 对应约 -50~50°C
        tile_humidity = env[1, i, j]     # 湿度 [0, 1]
        tile_elevation = env[2, i, j]    # 海拔（归一化）
        tile_resource = env[3, i, j]     # 资源 [0, 1]
        tile_land = env[4, i, j] if C > 4 else 1.0   # 陆地 0-1
        tile_ocean = env[5, i, j] if C > 5 else 0.0  # 海洋 0-1
        tile_coast = env[6, i, j] if C > 6 else 0.0  # 海岸 0-1
        
        # ========== 1. 温度适宜度（精确特质匹配）==========
        # 最适温度 = 基于耐热性和耐寒性的平衡点
        # 耐热10耐寒1 → 最适 +27°C，耐热1耐寒10 → 最适 -27°C
        optimal_temp_norm = (heat_res - cold_res) * 0.06  # 范围 [-0.54, +0.54] 对应约 [-27, +27]°C
        
        # 容忍范围 = 两个特质之和决定（特化物种范围窄）
        # 耐热10+耐寒10 = 宽范围(0.24)，耐热5+耐寒5 = 中等(0.12)
        temp_tolerance = (heat_res + cold_res) * 0.012
        
        temp_diff = ti.abs(tile_temp - optimal_temp_norm)
        
        temp_score = 0.0
        if temp_diff <= temp_tolerance:
            temp_score = 1.0
        else:
            # 超出容忍范围：指数衰减
            excess = temp_diff - temp_tolerance
            temp_score = ti.exp(-excess * 8.0)  # 快速衰减
        
        # ========== 2. 湿度/干旱适宜度 ==========
        # 耐旱性高 = 喜干燥
        optimal_humidity = 1.0 - drought_res * 0.08  # 范围 [0.2, 0.92]
        humidity_tolerance = 0.12 + drought_res * 0.02
        
        humidity_diff = ti.abs(tile_humidity - optimal_humidity)
        humidity_score = 0.0
        if humidity_diff <= humidity_tolerance:
            humidity_score = 1.0
        else:
            excess = humidity_diff - humidity_tolerance
            humidity_score = ti.max(0.0, 1.0 - excess * 4.0)
        
        # ========== 3. 盐度适宜度 ==========
        # 耐盐性高 = 适应海水
        optimal_salinity = salt_res * 0.1  # 范围 [0.1, 1.0]
        # 环境盐度：海洋=1.0，海岸=0.3，陆地=0
        tile_salinity = tile_ocean * 1.0 + tile_coast * 0.3
        
        salinity_diff = ti.abs(tile_salinity - optimal_salinity)
        salinity_score = ti.max(0.0, 1.0 - salinity_diff * 3.0)
        
        # ========== 4. 光照适宜度 ==========
        # 光照需求高 = 需要强光（浅水/地表）
        # 深海/深水 = 光照弱
        tile_light = 1.0 - tile_ocean * 0.7  # 海洋光照弱
        tile_light = ti.max(0.1, tile_light)
        
        optimal_light = light_req * 0.1
        light_diff = ti.abs(tile_light - optimal_light)
        light_score = ti.max(0.0, 1.0 - light_diff * 3.0)
        
        # ========== 5. 资源适宜度 ==========
        resource_score = ti.min(1.0, tile_resource * 1.2)
        
        # ========== 6. 栖息地匹配（硬约束）==========
        habitat_match = (
            tile_land * land_pref +
            tile_ocean * ocean_pref +
            tile_coast * coast_pref
        )
        
        # 硬约束检查
        is_land_only = land_pref > 0.7 and ocean_pref < 0.2
        is_ocean_only = ocean_pref > 0.7 and land_pref < 0.2
        
        habitat_penalty = 1.0
        if is_land_only and tile_ocean > 0.5:
            # 陆生物种在海洋
            habitat_penalty = 0.0
        elif is_ocean_only and tile_land > 0.5 and tile_coast < 0.3:
            # 海洋物种在纯陆地
            habitat_penalty = 0.0
        
        # ========== 7. 综合宜居度（加权）==========
        base_suit = (
            temp_score * 0.30 +       # 温度最重要
            humidity_score * 0.18 +   # 湿度
            salinity_score * 0.18 +   # 盐度
            light_score * 0.12 +      # 光照
            resource_score * 0.12 +   # 资源
            habitat_match * 0.10      # 栖息地匹配
        )
        
        # 应用栖息地硬约束
        base_suit *= habitat_penalty
        
        # ========== 8. 专化度调节 ==========
        # 专化物种在最适环境中更强，在不适环境中更弱
        if specialization > 0.6:
            if base_suit > 0.65:
                # 专化物种在好环境中加成
                base_suit *= (1.0 + (specialization - 0.6) * 0.5)
            elif base_suit < 0.35:
                # 专化物种在差环境中惩罚更重
                base_suit *= (1.0 - (specialization - 0.6) * 0.8)
        elif specialization < 0.3:
            # 泛化物种：适宜度打折但更稳定
            base_suit *= (0.85 + specialization * 0.5)
        
        result[s, i, j] = ti.max(0.0, ti.min(1.0, base_suit))


@ti.kernel
def kernel_compute_local_fitness(
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """计算每个物种在每个地块的局部竞争适应度 - Taichi GPU 并行
    
    【核心】竞争适应度 = 环境适应 + 生命史特质
    
    Args:
        suitability: 宜居度张量 (S, H, W)
        species_traits: 物种特质 (S, 14)
        pop: 种群张量 (S, H, W)
        result: 局部适应度输出 (S, H, W)
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        suit = suitability[s, i, j]
        
        if pop[s, i, j] <= 0 or suit <= 0.01:
            result[s, i, j] = 0.0
            continue
        
        # 获取生命史特质
        repro_rate = species_traits[s, 5]    # 繁殖速度 1-10
        body_size = species_traits[s, 6]     # 体型 1-10
        mobility = species_traits[s, 7]      # 机动性 1-10
        age = species_traits[s, 12]          # 年龄
        
        # 繁殖效率（繁殖速度/体型：小而多产更有效率）
        repro_efficiency = repro_rate / ti.max(body_size, 1.0)
        repro_score = ti.min(1.0, repro_efficiency * 0.5)
        
        # 资源效率（小体型效率高）
        size_efficiency = (11.0 - body_size) / 10.0
        
        # 机动性优势
        mobility_score = mobility / 10.0
        
        # 年龄优势（新物种有进化优势）
        age_bonus = 1.0
        if age <= 2:
            age_bonus = 1.25
        elif age <= 5:
            age_bonus = 1.15
        elif age <= 10:
            age_bonus = 1.05
        elif age > 20:
            age_bonus = 0.90
        elif age > 30:
            age_bonus = 0.80
        
        # 综合局部适应度
        local_fitness = (
            suit * 0.40 +                    # 环境适应（最重要）
            repro_score * 0.25 +             # 繁殖效率
            size_efficiency * 0.15 +         # 资源效率
            mobility_score * 0.20            # 机动性
        ) * age_bonus
        
        result[s, i, j] = ti.max(0.0, ti.min(1.0, local_fitness))


@ti.kernel
def kernel_compute_niche_overlap_matrix(
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=2),
):
    """计算物种间多维生态位重叠矩阵 - Taichi GPU 并行
    
    【核心】使用6维生态位特征向量计算相似度
    只有高重叠的物种才真正竞争
    
    Args:
        species_traits: 物种特质 (S, 14)
        result: 生态位重叠矩阵 (S, S)
    """
    S = result.shape[0]
    
    for i, j in ti.ndrange(S, S):
        if i == j:
            result[i, j] = 1.0
            continue
        
        # 构建6维生态位特征向量
        # 物种 i 的生态位
        heat_i = species_traits[i, 0]
        cold_i = species_traits[i, 1]
        drought_i = species_traits[i, 2]
        salt_i = species_traits[i, 3]
        light_i = species_traits[i, 4]
        body_i = species_traits[i, 6]
        trophic_i = species_traits[i, 11]
        
        # 物种 j 的生态位
        heat_j = species_traits[j, 0]
        cold_j = species_traits[j, 1]
        drought_j = species_traits[j, 2]
        salt_j = species_traits[j, 3]
        light_j = species_traits[j, 4]
        body_j = species_traits[j, 6]
        trophic_j = species_traits[j, 11]
        
        # 归一化特征并计算加权欧氏距离
        # 温度生态位（耐热+耐寒的平均）
        temp_niche_i = (heat_i + cold_i) / 20.0
        temp_niche_j = (heat_j + cold_j) / 20.0
        
        # 湿度生态位
        humid_niche_i = drought_i / 10.0
        humid_niche_j = drought_j / 10.0
        
        # 盐度生态位
        salt_niche_i = salt_i / 10.0
        salt_niche_j = salt_j / 10.0
        
        # 光照生态位
        light_niche_i = light_i / 10.0
        light_niche_j = light_j / 10.0
        
        # 体型生态位
        size_niche_i = body_i / 10.0
        size_niche_j = body_j / 10.0
        
        # 营养级（权重最高）
        trophic_niche_i = trophic_i / 5.0
        trophic_niche_j = trophic_j / 5.0
        
        # 加权距离（营养级权重最高）
        dist_sq = (
            (temp_niche_i - temp_niche_j) ** 2 * 0.15 +
            (humid_niche_i - humid_niche_j) ** 2 * 0.12 +
            (salt_niche_i - salt_niche_j) ** 2 * 0.12 +
            (light_niche_i - light_niche_j) ** 2 * 0.08 +
            (size_niche_i - size_niche_j) ** 2 * 0.13 +
            (trophic_niche_i - trophic_niche_j) ** 2 * 0.40  # 营养级最重要
        )
        
        distance = ti.sqrt(dist_sq)
        
        # 高斯核转换为相似度
        # 距离小 = 高重叠 = 强竞争
        similarity = ti.exp(-distance * distance * 8.0)
        
        result[i, j] = similarity


@ti.kernel
def kernel_apply_trait_competition(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    local_fitness: ti.types.ndarray(dtype=ti.f32, ndim=3),
    niche_overlap: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    competition_strength: ti.f32,
):
    """应用基于特质的竞争计算 - Taichi GPU 并行
    
    【核心】使用局部适应度和生态位重叠决定竞争结果
    
    Args:
        pop: 种群张量 (S, H, W)
        local_fitness: 局部适应度 (S, H, W)
        niche_overlap: 生态位重叠矩阵 (S, S)
        result: 竞争后的种群 (S, H, W)
        competition_strength: 竞争强度系数
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        my_pop = pop[s, i, j]
        
        if my_pop <= 0:
            result[s, i, j] = 0.0
            continue
        
        my_fitness = local_fitness[s, i, j]
        
        # 计算来自所有竞争者的压力
        competition_pressure = 0.0
        
        for other in range(S):
            if other == s:
                continue
            
            other_pop = pop[other, i, j]
            if other_pop <= 0:
                continue
            
            # 生态位重叠（只有高重叠才有显著竞争）
            overlap = niche_overlap[s, other]
            if overlap < 0.3:
                # 低重叠：几乎不竞争
                continue
            
            other_fitness = local_fitness[other, i, j]
            
            # 适应度差异决定竞争结果
            fitness_diff = other_fitness - my_fitness
            
            if fitness_diff > 0.05:
                # 对方更强：我受压
                pressure = overlap * fitness_diff * other_pop * competition_strength
                competition_pressure += pressure
            elif fitness_diff < -0.05:
                # 我更强：对方受压，我略有增益（负压力）
                bonus = overlap * ti.abs(fitness_diff) * other_pop * competition_strength * 0.1
                competition_pressure -= bonus
            else:
                # 势均力敌：双方都有损耗
                pressure = overlap * other_pop * competition_strength * 0.3
                competition_pressure += pressure
        
        # 应用竞争压力
        loss_ratio = ti.min(0.5, competition_pressure / (my_pop + 100.0))
        result[s, i, j] = my_pop * (1.0 - loss_ratio)


@ti.kernel
def kernel_compute_distance_weights(
    current_pos: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    max_distance: ti.f32,
):
    """批量计算所有物种从当前位置到所有地块的距离权重 - Taichi 并行
    
    【v2.1修复】使用指数衰减而非线性衰减，确保远距离权重更低
    当物种没有种群时，返回0而非1（防止新物种出现在任何地方）
    
    Args:
        current_pos: 当前种群位置 (S, H, W) - 种群密度
        result: 距离权重输出 (S, H, W)
        max_distance: 最大迁徙距离
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        # 计算该物种的质心
        total_pop = 0.0
        center_i = 0.0
        center_j = 0.0
        
        for ii in range(H):
            for jj in range(W):
                pop = current_pos[s, ii, jj]
                if pop > 0:
                    total_pop += pop
                    center_i += ii * pop
                    center_j += jj * pop
        
        if total_pop > 0:
            center_i /= total_pop
            center_j /= total_pop
            
            # 曼哈顿距离
            dist = ti.abs(ti.cast(i, ti.f32) - center_i) + ti.abs(ti.cast(j, ti.f32) - center_j)
            
            # 【v2.1修复】使用指数衰减：exp(-dist / max_distance)
            # 距离越远权重越低，超过 max_distance 后权重趋近于0
            if dist <= max_distance:
                # 指数衰减，距离=max_distance时权重≈0.37
                result[s, i, j] = ti.exp(-dist / max_distance)
            else:
                # 超出最大距离，权重为0
                result[s, i, j] = 0.0
        else:
            # 【v2.1修复】没有种群时权重为0，防止物种"瞬移"到任何地方
            result[s, i, j] = 0.0


@ti.kernel
def kernel_compute_prey_density(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    consumer_idx: ti.i32,
    result: ti.types.ndarray(dtype=ti.f32, ndim=2),
):
    """计算消费者的猎物密度分布 - Taichi 并行
    
    Args:
        pop: 种群张量 (S, H, W)
        trophic_levels: 营养级数组 (S,)
        consumer_idx: 消费者物种索引
        result: 猎物密度输出 (H, W)
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    consumer_trophic = trophic_levels[consumer_idx]
    
    for i, j in ti.ndrange(H, W):
        prey_density = 0.0
        
        for s in range(S):
            # 猎物的营养级应该比消费者低约1级
            if trophic_levels[s] < consumer_trophic and trophic_levels[s] >= consumer_trophic - 1.5:
                prey_density += pop[s, i, j]
        
        result[i, j] = prey_density


@ti.kernel
def kernel_migration_decision(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    distance_weights: ti.types.ndarray(dtype=ti.f32, ndim=3),
    death_rates: ti.types.ndarray(dtype=ti.f32, ndim=1),
    migration_scores: ti.types.ndarray(dtype=ti.f32, ndim=3),
    pressure_threshold: ti.f32,
    saturation_threshold: ti.f32,
):
    """批量计算所有物种的迁徙决策分数 - Taichi 并行 (v2.3 修复版)
    
    【v2.3核心修复】
    1. 降低宜居度阈值：从0.25降到0.15
    2. 增强压力驱动：死亡率高时更强烈地迁徙
    3. 考虑源地块宜居度：源地块差时更愿意迁走
    
    Args:
        pop: 种群张量 (S, H, W)
        suitability: 适宜度张量 (S, H, W)
        distance_weights: 距离权重张量 (S, H, W)
        death_rates: 每个物种的死亡率 (S,)
        migration_scores: 迁徙分数输出 (S, H, W)
        pressure_threshold: 压力迁徙阈值
        saturation_threshold: 饱和度阈值
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    # 【修改】降低迁徙目标的宜居度阈值
    MIGRATION_SUIT_THRESHOLD = 0.15  # 从0.25降低到0.15
    SOURCE_LOW_SUIT_THRESHOLD = 0.25 # 源地块低宜居度阈值
    
    for s, i, j in ti.ndrange(S, H, W):
        # 默认分数为0
        migration_scores[s, i, j] = 0.0
        
        # 当前地块已有种群，不需要迁入
        if pop[s, i, j] > 0:
            continue
        # 适宜度太低的地块不接收迁徙（使用降低后的阈值）
        if suitability[s, i, j] < MIGRATION_SUIT_THRESHOLD:
            continue
        
        # 检查是否与已有种群相邻（4邻域）+ 检查源地块宜居度
        adj_count = 0
        adj_suit_total = 0.0
        has_low_suit_source = False
        
        if i > 0:
            if pop[s, i - 1, j] > 0:
                adj_count += 1
                adj_suit_total += suitability[s, i - 1, j]
                if suitability[s, i - 1, j] < SOURCE_LOW_SUIT_THRESHOLD:
                    has_low_suit_source = True
        if i < H - 1:
            if pop[s, i + 1, j] > 0:
                adj_count += 1
                adj_suit_total += suitability[s, i + 1, j]
                if suitability[s, i + 1, j] < SOURCE_LOW_SUIT_THRESHOLD:
                    has_low_suit_source = True
        if j > 0:
            if pop[s, i, j - 1] > 0:
                adj_count += 1
                adj_suit_total += suitability[s, i, j - 1]
                if suitability[s, i, j - 1] < SOURCE_LOW_SUIT_THRESHOLD:
                    has_low_suit_source = True
        if j < W - 1:
            if pop[s, i, j + 1] > 0:
                adj_count += 1
                adj_suit_total += suitability[s, i, j + 1]
                if suitability[s, i, j + 1] < SOURCE_LOW_SUIT_THRESHOLD:
                    has_low_suit_source = True
        
        # 只有与已有种群相邻的地块才能获得迁徙分数
        if adj_count > 0:
            death_rate = death_rates[s]
            target_suit = suitability[s, i, j]
            avg_source_suit = adj_suit_total / ti.cast(adj_count, ti.f32)
            
            # 基础分数
            base_score = target_suit * 0.6 + distance_weights[s, i, j] * 0.4
            
            # 【新增】低宜居度逃逸加成
            if has_low_suit_source and target_suit > avg_source_suit:
                escape_bonus = (target_suit - avg_source_suit) * 1.2
                base_score += escape_bonus
            
            # 压力驱动迁徙 - 死亡率高时更愿意迁移（增强）
            if death_rate > pressure_threshold:
                pressure_boost = ti.min(0.7, (death_rate - pressure_threshold) * 2.5)
                base_score = target_suit * (0.7 + pressure_boost * 0.2) + distance_weights[s, i, j] * (0.3 - pressure_boost * 0.1)
                base_score *= (1.0 + pressure_boost * 0.8)
            
            # 添加随机扰动（用格子坐标模拟）
            noise = 0.9 + 0.2 * ti.sin(ti.cast(i * 17 + j * 31 + s * 7, ti.f32))
            migration_scores[s, i, j] = base_score * noise


@ti.kernel
def kernel_migration_decision_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    distance_weights: ti.types.ndarray(dtype=ti.f32, ndim=3),
    death_rates: ti.types.ndarray(dtype=ti.f32, ndim=1),
    resource_pressure: ti.types.ndarray(dtype=ti.f32, ndim=1),
    prey_density: ti.types.ndarray(dtype=ti.f32, ndim=3),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    migration_scores: ti.types.ndarray(dtype=ti.f32, ndim=3),
    pressure_threshold: ti.f32,
    saturation_threshold: ti.f32,
    oversaturation_threshold: ti.f32,
    prey_scarcity_threshold: ti.f32,
    prey_weight: ti.f32,
    oversat_bonus: ti.f32,
    consumer_trophic_threshold: ti.f32,
):
    """迁徙决策 v3.0 - 加入栖息地类型约束
    
    【v3.0 修复】:
    1. 加入栖息地类型检查：陆地物种不能迁徙到海洋，反之亦然
    2. 只允许向连通的同类型栖息地迁徙
    3. 完全禁用跨栖息地迁徙（即使宜居度高）
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C = env.shape[0]
    
    MIGRATION_SUIT_THRESHOLD = 0.15
    SOURCE_LOW_SUIT_THRESHOLD = 0.25
    
    for s, i, j in ti.ndrange(S, H, W):
        migration_scores[s, i, j] = 0.0
        
        # 目标地块已有种群，不需要迁入
        if pop[s, i, j] > 0:
            continue
        # 目标地块宜居度太低
        if suitability[s, i, j] < MIGRATION_SUIT_THRESHOLD:
            continue
        
        # 【新增】获取物种栖息地偏好
        land_pref = species_traits[s, 8]
        ocean_pref = species_traits[s, 9]
        coast_pref = species_traits[s, 10]
        
        # 判断物种类型
        is_terrestrial = land_pref > 0.5 and ocean_pref < 0.4
        is_aquatic = ocean_pref > 0.5 and land_pref < 0.4
        is_amphibious = coast_pref > 0.4 or (land_pref > 0.3 and ocean_pref > 0.3)
        
        # 【新增】获取目标地块栖息地类型
        target_land = env[4, i, j] if C > 4 else 1.0
        target_ocean = env[5, i, j] if C > 5 else 0.0
        target_coast = env[6, i, j] if C > 6 else 0.0
        
        # 【关键】栖息地类型硬约束检查
        habitat_ok = True
        if is_terrestrial and not is_amphibious:
            # 陆地物种不能迁入纯海洋
            if target_ocean > 0.6 and target_coast < 0.3:
                habitat_ok = False
        elif is_aquatic and not is_amphibious:
            # 海洋物种不能迁入纯陆地
            if target_land > 0.6 and target_coast < 0.3:
                habitat_ok = False
        
        if not habitat_ok:
            continue
        
        # 相邻性检查 + 栖息地连通性检查
        adj_count = 0
        adj_pop_total = 0.0
        adj_suit_total = 0.0
        has_low_suit_source = False
        has_habitat_connected_source = False  # 是否有栖息地连通的源
        
        # 检查四个邻居
        for di, dj in ti.static([(-1, 0), (1, 0), (0, -1), (0, 1)]):
            ni = i + di
            nj = j + dj
            if 0 <= ni < H and 0 <= nj < W:
                if pop[s, ni, nj] > 0:
                    # 【新增】检查源地块与目标地块的栖息地连通性
                    src_land = env[4, ni, nj] if C > 4 else 1.0
                    src_ocean = env[5, ni, nj] if C > 5 else 0.0
                    src_coast = env[6, ni, nj] if C > 6 else 0.0
                    
                    # 判断是否连通（同类型或通过海岸过渡）
                    is_connected = False
                    if is_terrestrial:
                        # 陆地物种：源和目标都是陆地/海岸
                        if (src_land > 0.3 or src_coast > 0.3) and (target_land > 0.3 or target_coast > 0.3):
                            is_connected = True
                    elif is_aquatic:
                        # 海洋物种：源和目标都是海洋/海岸
                        if (src_ocean > 0.3 or src_coast > 0.3) and (target_ocean > 0.3 or target_coast > 0.3):
                            is_connected = True
                    else:
                        # 两栖物种：任何相邻都算连通
                        is_connected = True
                    
                    if is_connected:
                        adj_count += 1
                        adj_pop_total += pop[s, ni, nj]
                        adj_suit_total += suitability[s, ni, nj]
                        has_habitat_connected_source = True
                        if suitability[s, ni, nj] < SOURCE_LOW_SUIT_THRESHOLD:
                            has_low_suit_source = True
        
        # 【关键】必须有栖息地连通的源才能迁徙
        if adj_count == 0 or not has_habitat_connected_source:
            continue
        
        death_rate = death_rates[s]
        res_pressure = resource_pressure[s]
        target_suit = suitability[s, i, j]
        avg_source_suit = adj_suit_total / ti.cast(adj_count, ti.f32)
        
        # 基础分数
        base_score = target_suit * 0.5 + distance_weights[s, i, j] * 0.5
        
        # 低宜居度逃逸加成
        if has_low_suit_source and target_suit > avg_source_suit:
            escape_bonus = (target_suit - avg_source_suit) * 1.5
            base_score += escape_bonus
        
        # 目标地块比源地块好很多时，额外加分
        if target_suit > avg_source_suit + 0.15:
            improvement_bonus = (target_suit - avg_source_suit) * 0.8
            base_score += improvement_bonus
        
        # 压力驱动
        if death_rate > pressure_threshold:
            pressure_boost = ti.min(0.8, (death_rate - pressure_threshold) * 3.0)
            base_score = (
                target_suit * (0.7 + pressure_boost * 0.2) +
                distance_weights[s, i, j] * (0.3 - pressure_boost * 0.1)
            )
            base_score *= (1.0 + pressure_boost * 0.8)
        
        # 饱和/过饱和
        if res_pressure > saturation_threshold:
            base_score = target_suit * 0.5 + distance_weights[s, i, j] * 0.5
            base_score *= 1.2
        if res_pressure > oversaturation_threshold:
            base_score *= (1.0 + oversat_bonus * 1.5)
        
        # 猎物追踪
        if trophic_levels[s] >= consumer_trophic_threshold:
            prey_val = prey_density[s, i, j]
            if prey_val < prey_scarcity_threshold:
                base_score = (
                    base_score * (1.0 - prey_weight) +
                    prey_val * target_suit * prey_weight
                )
            elif prey_val > prey_scarcity_threshold * 2.0:
                base_score *= 1.3
        
        noise = 0.9 + 0.2 * ti.sin(ti.cast(i * 17 + j * 31 + s * 11, ti.f32))
        migration_scores[s, i, j] = base_score * noise


@ti.kernel
def kernel_execute_migration(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    migration_scores: ti.types.ndarray(dtype=ti.f32, ndim=3),
    distance_weights: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    migration_rates: ti.types.ndarray(dtype=ti.f32, ndim=1),
    score_threshold: ti.f32,
    long_jump_prob: ti.f32,
):
    """执行迁徙 v3.0 - 加入栖息地连通性检查
    
    【v3.0 修复】
    1. 物种只能向同类型栖息地迁徙
    2. long_jump 完全禁用跨栖息地类型的跳跃
    3. 海洋物种不能跳到内陆湖（必须有水路连通）
    
    Args:
        pop: 当前种群张量 (S, H, W)
        migration_scores: 迁徙分数张量 (S, H, W)
        distance_weights: 距离权重张量 (S, H, W)
        species_traits: 物种特质 (S, 14)
        env: 环境张量 (C, H, W)
        new_pop: 迁徙后的种群张量 (S, H, W)
        migration_rates: 每个物种的迁徙比例 (S,)
        score_threshold: 分数阈值
        long_jump_prob: 非相邻迁徙概率（严格限制）
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C = env.shape[0]
    
    for s in range(S):
        # 获取物种栖息地偏好
        land_pref = species_traits[s, 8]
        ocean_pref = species_traits[s, 9]
        coast_pref = species_traits[s, 10]
        
        is_terrestrial = land_pref > 0.5 and ocean_pref < 0.4
        is_aquatic = ocean_pref > 0.5 and land_pref < 0.4
        is_amphibious = coast_pref > 0.4 or (land_pref > 0.3 and ocean_pref > 0.3)
        
        # 第一遍：计算该物种的总种群和现有栖息地类型
        total_pop = 0.0
        has_land_pop = False
        has_ocean_pop = False
        
        for i, j in ti.ndrange(H, W):
            if pop[s, i, j] > 0:
                total_pop += pop[s, i, j]
                tile_land = env[4, i, j] if C > 4 else 1.0
                tile_ocean = env[5, i, j] if C > 5 else 0.0
                if tile_land > 0.5:
                    has_land_pop = True
                if tile_ocean > 0.5:
                    has_ocean_pop = True
        
        # 第二遍：计算有效迁徙分数（带栖息地约束）
        total_score = 0.0
        for i, j in ti.ndrange(H, W):
            if pop[s, i, j] <= 0 and migration_scores[s, i, j] > score_threshold:
                # 获取目标地块栖息地类型
                target_land = env[4, i, j] if C > 4 else 1.0
                target_ocean = env[5, i, j] if C > 5 else 0.0
                target_coast = env[6, i, j] if C > 6 else 0.0
                
                # 【关键】检查栖息地类型匹配
                habitat_ok = True
                if is_terrestrial and not is_amphibious:
                    if target_ocean > 0.6 and target_coast < 0.3:
                        habitat_ok = False
                elif is_aquatic and not is_amphibious:
                    if target_land > 0.6 and target_coast < 0.3:
                        habitat_ok = False
                
                if not habitat_ok:
                    continue
                
                # 检查相邻性 + 栖息地连通性
                adj_count = 0
                has_connected_source = False
                
                for di, dj in ti.static([(-1, 0), (1, 0), (0, -1), (0, 1)]):
                    ni = i + di
                    nj = j + dj
                    if 0 <= ni < H and 0 <= nj < W:
                        if pop[s, ni, nj] > 0:
                            # 检查源地块与目标地块是否栖息地连通
                            src_land = env[4, ni, nj] if C > 4 else 1.0
                            src_ocean = env[5, ni, nj] if C > 5 else 0.0
                            src_coast = env[6, ni, nj] if C > 6 else 0.0
                            
                            is_connected = False
                            if is_terrestrial:
                                if (src_land > 0.3 or src_coast > 0.3) and (target_land > 0.3 or target_coast > 0.3):
                                    is_connected = True
                            elif is_aquatic:
                                if (src_ocean > 0.3 or src_coast > 0.3) and (target_ocean > 0.3 or target_coast > 0.3):
                                    is_connected = True
                            else:
                                is_connected = True
                            
                            if is_connected:
                                adj_count += 1
                                has_connected_source = True
                
                # 相邻且连通的地块
                if adj_count > 0 and has_connected_source:
                    total_score += migration_scores[s, i, j]
                else:
                    # long_jump：严格限制 - 必须目标与现有种群是同类型栖息地
                    if long_jump_prob > 0 and migration_scores[s, i, j] > score_threshold * 1.5 and distance_weights[s, i, j] > 0.0:
                        # 【严格检查】long_jump 只能跳到与现有种群同类型的栖息地
                        long_jump_ok = False
                        if is_terrestrial and has_land_pop and (target_land > 0.5 or target_coast > 0.3):
                            long_jump_ok = True
                        elif is_aquatic and has_ocean_pop and (target_ocean > 0.5 or target_coast > 0.3):
                            long_jump_ok = True
                        elif is_amphibious:
                            long_jump_ok = True
                        
                        if long_jump_ok:
                            noise = 0.5 + 0.5 * ti.sin(ti.cast(i * 13 + j * 17 + s * 19, ti.f32))
                            # 【降低 long_jump 概率】避免跳到不连通的地方
                            if noise < long_jump_prob * 3.0:
                                total_score += migration_scores[s, i, j]
        
        # 迁徙量
        migrate_amount = total_pop * migration_rates[s]
        
        # 第三遍：按分数比例分配迁徙种群
        for i, j in ti.ndrange(H, W):
            if pop[s, i, j] > 0:
                new_pop[s, i, j] = pop[s, i, j] * (1.0 - migration_rates[s])
            else:
                new_pop[s, i, j] = 0.0
                
                if total_score > 0 and migration_scores[s, i, j] > score_threshold:
                    # 获取目标地块栖息地类型
                    target_land = env[4, i, j] if C > 4 else 1.0
                    target_ocean = env[5, i, j] if C > 5 else 0.0
                    target_coast = env[6, i, j] if C > 6 else 0.0
                    
                    # 栖息地类型检查
                    habitat_ok = True
                    if is_terrestrial and not is_amphibious:
                        if target_ocean > 0.6 and target_coast < 0.3:
                            habitat_ok = False
                    elif is_aquatic and not is_amphibious:
                        if target_land > 0.6 and target_coast < 0.3:
                            habitat_ok = False
                    
                    if not habitat_ok:
                        continue
                    
                    # 检查相邻性
                    adj_count = 0
                    has_connected_source = False
                    
                    for di, dj in ti.static([(-1, 0), (1, 0), (0, -1), (0, 1)]):
                        ni = i + di
                        nj = j + dj
                        if 0 <= ni < H and 0 <= nj < W:
                            if pop[s, ni, nj] > 0:
                                src_land = env[4, ni, nj] if C > 4 else 1.0
                                src_ocean = env[5, ni, nj] if C > 5 else 0.0
                                src_coast = env[6, ni, nj] if C > 6 else 0.0
                                
                                is_connected = False
                                if is_terrestrial:
                                    if (src_land > 0.3 or src_coast > 0.3) and (target_land > 0.3 or target_coast > 0.3):
                                        is_connected = True
                                elif is_aquatic:
                                    if (src_ocean > 0.3 or src_coast > 0.3) and (target_ocean > 0.3 or target_coast > 0.3):
                                        is_connected = True
                                else:
                                    is_connected = True
                                
                                if is_connected:
                                    adj_count += 1
                                    has_connected_source = True
                    
                    allow_long = False
                    if adj_count == 0 and long_jump_prob > 0 and distance_weights[s, i, j] > 0.0:
                        long_jump_ok = False
                        if is_terrestrial and has_land_pop and (target_land > 0.5 or target_coast > 0.3):
                            long_jump_ok = True
                        elif is_aquatic and has_ocean_pop and (target_ocean > 0.5 or target_coast > 0.3):
                            long_jump_ok = True
                        elif is_amphibious:
                            long_jump_ok = True
                        
                        if long_jump_ok:
                            noise = 0.5 + 0.5 * ti.sin(ti.cast((i + 1) * 23 + (j + 1) * 29 + s * 31, ti.f32))
                            allow_long = noise < long_jump_prob * 3.0
                    
                    if (adj_count > 0 and has_connected_source) or allow_long:
                        score_ratio = migration_scores[s, i, j] / total_score
                        new_pop[s, i, j] = migrate_amount * score_ratio


@ti.kernel
def kernel_advanced_diffusion(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
):
    """带适宜度引导和密度驱动的高级扩散 - Taichi 并行
    
    【v2.3 修复】三重扩散机制：
    1. 适宜度梯度扩散：向更适宜的地方流动
    2. 密度压力扩散：高密度区域强制向低密度区域扩散（关键！）
    3. 低宜居度逃逸：从不适宜区域逃离
    
    Args:
        pop: 种群张量 (S, H, W)
        suitability: 适宜度张量 (S, H, W)
        new_pop: 扩散后的种群张量 (S, H, W)
        base_rate: 基础扩散率
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    # 适宜度阈值
    SUIT_THRESHOLD = 0.20          # 正常扩散的宜居度阈值（降低）
    SUIT_LOW_THRESHOLD = 0.10      # 低宜居度阈值（降低）
    SUIT_ESCAPE_THRESHOLD = 0.15   # 触发逃逸的宜居度阈值
    
    # 【新增】密度压力参数
    DENSITY_PRESSURE_THRESHOLD = 50.0    # 密度压力阈值（当前格子种群数）
    DENSITY_PRESSURE_RATE = 1.5          # 密度压力扩散倍率
    CROWDING_THRESHOLD = 100.0           # 拥挤阈值（强制扩散）
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        my_suit = suitability[s, i, j]
        
        # 计算流入和流出
        outflow = 0.0
        inflow = 0.0
        density_outflow = 0.0   # 【新增】密度压力驱动的流出
        escape_outflow = 0.0    # 逃逸流出
        
        # 四个邻居方向
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        # 统计邻居信息
        any_better_neighbor = False
        any_lower_density_neighbor = False
        total_neighbor_pop = 0.0
        valid_neighbor_count = 0
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                neighbor_suit = suitability[s, ni, nj]
                neighbor_pop = pop[s, ni, nj]
                valid_neighbor_count += 1
                total_neighbor_pop += neighbor_pop
                
                if neighbor_suit > my_suit:
                    any_better_neighbor = True
                if neighbor_pop < current * 0.5:  # 邻居密度明显低于我
                    any_lower_density_neighbor = True
                
                # 适宜度梯度
                gradient = neighbor_suit - my_suit
                # 密度梯度：正值表示我的密度更高
                density_gradient = current - neighbor_pop
                
                # === 流出计算：当前地块有种群 ===
                if current > 0:
                    # 【机制1】适宜度梯度扩散：向更好的地方流动
                    if neighbor_suit > SUIT_THRESHOLD:
                        if gradient > 0:
                            # 向高适宜度流出
                            rate = base_rate * (1.0 + gradient * 0.5)
                            outflow += current * rate * 0.25
                        elif gradient > -0.3:
                            # 邻居适宜度稍低但可接受
                            rate = base_rate * 0.4
                            outflow += current * rate * 0.25
                    
                    # 【机制2 - 关键】密度压力扩散：从高密度向低密度流动
                    # 即使邻居适宜度不如当前，只要密度低且适宜度过得去，就扩散
                    if current > DENSITY_PRESSURE_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                        if density_gradient > 0:  # 我的密度更高
                            # 密度压力：密度越高，扩散越强
                            pressure_factor = ti.min(2.0, current / DENSITY_PRESSURE_THRESHOLD)
                            rate = base_rate * DENSITY_PRESSURE_RATE * pressure_factor * (density_gradient / (current + 1.0))
                            density_outflow += current * rate * 0.25
                    
                    # 【机制2b】极端拥挤：强制扩散
                    if current > CROWDING_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                        # 极端拥挤：不管梯度，都要扩散出去
                        crowding_rate = base_rate * 2.0 * (current / CROWDING_THRESHOLD)
                        density_outflow += current * crowding_rate * 0.15
                    
                    # 【机制3】低宜居度逃逸
                    if neighbor_suit > SUIT_LOW_THRESHOLD and my_suit < SUIT_ESCAPE_THRESHOLD:
                        if gradient > 0:
                            escape_rate = base_rate * 2.0 * gradient
                            escape_outflow += current * escape_rate * 0.25
                
                # === 流入计算：邻居有种群 ===
                if neighbor_pop > 0:
                    # 情况1: 我的适宜度>阈值，正常流入
                    if my_suit > SUIT_THRESHOLD:
                        if gradient < 0:
                            rate = base_rate * (1.0 - gradient * 0.5)
                            inflow += neighbor_pop * rate * 0.25
                        elif gradient < 0.3:
                            rate = base_rate * 0.4
                            inflow += neighbor_pop * rate * 0.25
                    
                    # 情况2: 我的宜居度在低阈值以上，允许少量流入
                    elif my_suit > SUIT_LOW_THRESHOLD:
                        # 【新增】密度驱动流入：如果邻居很拥挤，接收一些
                        if neighbor_pop > DENSITY_PRESSURE_THRESHOLD and current < neighbor_pop * 0.5:
                            rate = base_rate * 0.8 * (neighbor_pop / CROWDING_THRESHOLD)
                            inflow += neighbor_pop * rate * 0.25
                        elif gradient < 0:
                            rate = base_rate * 0.3 * ti.abs(gradient)
                            inflow += neighbor_pop * rate * 0.25
        
        # 【新增】全局逃逸：当所有邻居都很差且密度高时
        random_escape = 0.0
        if current > 0:
            if my_suit < SUIT_ESCAPE_THRESHOLD and not any_better_neighbor:
                noise = 0.5 + 0.5 * ti.sin(ti.cast(i * 13 + j * 17 + s * 7, ti.f32))
                if noise > 0.6:  # 40%概率触发随机逃逸
                    random_escape = current * base_rate * 0.15
            # 【新增】高密度无处可去时，也要强制流出一些（避免无限堆积）
            elif current > CROWDING_THRESHOLD * 1.5 and not any_lower_density_neighbor:
                random_escape = current * base_rate * 0.10
        
        # 限制最大流出（不能超过当前种群的60%，进一步增加上限）
        total_outflow = outflow + density_outflow + escape_outflow + random_escape
        if current > 0:
            total_outflow = ti.min(total_outflow, current * 0.60)
        else:
            total_outflow = 0.0
        
        new_pop[s, i, j] = current - total_outflow + inflow


# ============================================================================
# 多因子死亡率内核 - GPU 加速完整生态死亡率计算
# ============================================================================

@ti.kernel
def kernel_multifactor_mortality(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_prefs: ti.types.ndarray(dtype=ti.f32, ndim=2),
    species_params: ti.types.ndarray(dtype=ti.f32, ndim=2),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    pressure_overlay: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_mortality: ti.f32,
    temp_weight: ti.f32,
    competition_weight: ti.f32,
    resource_weight: ti.f32,
    capacity_multiplier: ti.f32,
    era_scaling: ti.f32,
):
    """多因子死亡率计算 - Taichi 全并行
    
    综合以下因子：
    1. 温度压力
    2. 湿度压力
    3. 竞争压力（同地块物种竞争）
    4. 资源压力（承载力）
    5. 营养级压力（捕食/被捕食）
    6. 外部压力（灾害等）
    7. 【新增】宜居度压力 - 低宜居度导致高死亡
    8. 【新增】栖息地不匹配压力 - 陆/海偏好不匹配导致高死亡
    
    Args:
        pop: 种群张量 (S, H, W)
        env: 环境张量 (C, H, W) - [temp, humidity, altitude, resource, land, sea, coast]
        species_prefs: 物种偏好 (S, 7) - [温度, 湿度, 海拔, 资源, 陆地, 海洋, 海岸]
        species_params: 物种参数 (S, F) - 包含耐受性等
        trophic_levels: 营养级 (S,)
        pressure_overlay: 外部压力叠加 (C_pressure, H, W)
        result: 死亡率输出 (S, H, W)
        base_mortality: 基础死亡率
        temp_weight: 温度死亡率权重
        competition_weight: 竞争死亡率权重
        resource_weight: 资源死亡率权重
        capacity_multiplier: 承载力乘数
        era_scaling: 时代缩放因子
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C_env = env.shape[0]
    C_pressure = pressure_overlay.shape[0]
    
    # 宜居度相关阈值
    SUIT_LOW_THRESHOLD = 0.25      # 低宜居度阈值
    SUIT_CRITICAL_THRESHOLD = 0.10 # 极低宜居度阈值（几乎不可生存）
    SUIT_DEATH_WEIGHT = 0.35       # 宜居度死亡权重
    HABITAT_MISMATCH_PENALTY = 0.50  # 栖息地不匹配的死亡惩罚
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] <= 0:
            result[s, i, j] = 0.0
            continue
        
        # === 1. 温度死亡率 ===
        temp_channel = 0 if C_env > 0 else 0
        temp = env[temp_channel, i, j]
        temp_pref = species_prefs[s, 0] * 50.0  # 偏好范围 -50~50
        temp_deviation = ti.abs(temp - temp_pref)
        
        # 温度耐受性
        temp_tolerance = 15.0
        if species_params.shape[1] >= 2:
            temp_tolerance = ti.max(5.0, species_params[s, 1])
        
        temp_mortality = 1.0 - ti.exp(-temp_deviation / temp_tolerance)
        temp_mortality = ti.max(0.01, ti.min(0.8, temp_mortality))
        
        # === 2. 湿度死亡率 ===
        humidity = env[1, i, j] if C_env > 1 else 0.5
        humidity_pref = species_prefs[s, 1]
        humidity_deviation = ti.abs(humidity - humidity_pref)
        humidity_mortality = ti.min(0.4, humidity_deviation * 0.5)
        
        # === 3. 竞争死亡率 ===
        total_pop_tile = 0.0
        for sp in range(S):
            total_pop_tile += pop[sp, i, j]
        
        my_pop = ti.max(pop[s, i, j], 1e-6)
        competitor_pop = total_pop_tile - pop[s, i, j]
        competition_ratio = competitor_pop / (my_pop + 100.0)
        competition_mortality = ti.min(0.3, competition_ratio * 0.1)
        
        # === 4. 资源死亡率 ===
        resources = env[3, i, j] if C_env > 3 else 100.0
        capacity = resources * capacity_multiplier
        saturation = total_pop_tile / (capacity + 1e-6)
        resource_mortality = ti.max(0.0, ti.min(0.4, (saturation - 0.5) * 0.4))
        
        # === 5. 营养级死亡率 ===
        # 消费者（T>=2）在缺乏猎物时死亡率上升
        my_trophic = trophic_levels[s]
        prey_scarcity_mortality = 0.0
        
        if my_trophic >= 2.0:
            # 计算猎物密度
            prey_density = 0.0
            for sp in range(S):
                prey_trophic = trophic_levels[sp]
                if prey_trophic < my_trophic and prey_trophic >= my_trophic - 1.5:
                    prey_density += pop[sp, i, j]
            
            # 归一化
            prey_density_norm = prey_density / (total_pop_tile + 1e-6)
            # 【加强】猎物稀缺时死亡率更高
            if prey_density_norm < 0.20:
                prey_scarcity_mortality = (0.20 - prey_density_norm) * 1.5 + 0.1
            else:
                prey_scarcity_mortality = (1.0 - prey_density_norm) * 0.15
        
        # === 6. 外部压力死亡率 ===
        external_pressure = 0.0
        for c in range(C_pressure):
            external_pressure += pressure_overlay[c, i, j]
        external_mortality = ti.min(0.5, external_pressure * 0.1)
        
        # === 7. 【新增】宜居度死亡率 ===
        # 计算该物种在该地块的宜居度（简化版，综合温度+湿度+栖息地匹配）
        temp_diff = ti.abs(env[temp_channel, i, j] - species_prefs[s, 0])
        temp_match = ti.max(0.0, 1.0 - temp_diff * 2.0)
        humidity_match = ti.max(0.0, 1.0 - humidity_deviation * 2.0)
        
        # 栖息地匹配
        habitat_match = 0.0
        if C_env >= 7:
            habitat_match = (
                env[4, i, j] * species_prefs[s, 4] +  # 陆地
                env[5, i, j] * species_prefs[s, 5] +  # 海洋
                env[6, i, j] * species_prefs[s, 6]    # 海岸
            )
        else:
            habitat_match = 0.5  # 无栖息地信息时给中性值
        
        # 综合宜居度
        suitability = temp_match * 0.35 + humidity_match * 0.25 + habitat_match * 0.40
        suitability = ti.max(0.0, ti.min(1.0, suitability))
        
        # 宜居度死亡率：低宜居度导致高死亡
        suit_mortality = 0.0
        if suitability < SUIT_CRITICAL_THRESHOLD:
            # 极低宜居度：非常高的死亡率（几乎必死）
            suit_mortality = 0.70
        elif suitability < SUIT_LOW_THRESHOLD:
            # 低宜居度：较高死亡率，线性增加
            # 从 0.10 到 0.25，死亡率从 0.50 降到 0.15
            suit_mortality = 0.50 - (suitability - SUIT_CRITICAL_THRESHOLD) / (SUIT_LOW_THRESHOLD - SUIT_CRITICAL_THRESHOLD) * 0.35
        else:
            # 正常宜居度：轻微惩罚（1 - suitability）
            suit_mortality = (1.0 - suitability) * 0.10
        
        # === 8. 【新增】栖息地不匹配死亡率 ===
        habitat_mismatch_mortality = 0.0
        if C_env >= 6 and species_prefs.shape[1] >= 6:
            is_land = env[4, i, j] > 0.5
            is_sea = env[5, i, j] > 0.5
            land_pref = species_prefs[s, 4]
            sea_pref = species_prefs[s, 5]
            
            # 陆生物种在海洋 → 高死亡
            if is_sea and land_pref > sea_pref + 0.3:
                habitat_mismatch_mortality = HABITAT_MISMATCH_PENALTY
            # 海洋物种在陆地 → 高死亡  
            elif is_land and sea_pref > land_pref + 0.3:
                habitat_mismatch_mortality = HABITAT_MISMATCH_PENALTY
        
        # === 综合死亡率 ===
        total_mortality = (
            temp_mortality * temp_weight +
            humidity_mortality * 0.1 +
            competition_mortality * competition_weight +
            resource_mortality * resource_weight +
            prey_scarcity_mortality +
            external_mortality +
            suit_mortality * SUIT_DEATH_WEIGHT +      # 【新增】宜居度死亡
            habitat_mismatch_mortality +              # 【新增】栖息地不匹配死亡
            base_mortality
        )
        
        # 时代缩放：【调整】减少对死亡率的减免，避免"不死"问题
        if era_scaling > 1.5:
            # 缩放因子改为更保守的值（0.85 而非 0.7）
            scale_factor = ti.max(0.85, 1.0 / ti.pow(era_scaling, 0.15))
            total_mortality *= scale_factor
        
        result[s, i, j] = ti.max(0.02, ti.min(0.95, total_mortality))


@ti.kernel
def kernel_trait_mortality(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    pressure_overlay: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_mortality: ti.f32,
    era_scaling: ti.f32,
):
    """基于特质的精确死亡率计算 - Taichi GPU 全并行
    
    【核心改进】每个环境因素的死亡率由对应特质决定
    
    Args:
        pop: 种群张量 (S, H, W)
        env: 环境张量 (C, H, W)
        species_traits: 物种特质 (S, 14)
        suitability: 预计算的宜居度 (S, H, W)
        pressure_overlay: 外部压力叠加 (C_pressure, H, W)
        result: 死亡率输出 (S, H, W)
        base_mortality: 基础死亡率
        era_scaling: 时代缩放因子
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C_env = env.shape[0]
    C_pressure = pressure_overlay.shape[0]
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] <= 0:
            result[s, i, j] = 0.0
            continue
        
        # 获取物种特质
        heat_res = species_traits[s, 0]      # 耐热性 1-10
        cold_res = species_traits[s, 1]      # 耐寒性 1-10
        drought_res = species_traits[s, 2]   # 耐旱性 1-10
        salt_res = species_traits[s, 3]      # 耐盐性 1-10
        body_size = species_traits[s, 6]     # 体型 1-10
        land_pref = species_traits[s, 8]     # 陆地偏好
        ocean_pref = species_traits[s, 9]    # 海洋偏好
        trophic = species_traits[s, 11]      # 营养级
        
        # 获取环境参数
        tile_temp = env[0, i, j]             # 归一化温度
        tile_humidity = env[1, i, j] if C_env > 1 else 0.5
        tile_resource = env[3, i, j] if C_env > 3 else 0.5
        tile_land = env[4, i, j] if C_env > 4 else 1.0
        tile_ocean = env[5, i, j] if C_env > 5 else 0.0
        
        # ========== 1. 温度压力死亡率（特质精确计算）==========
        # 最适温度基于耐热性和耐寒性
        optimal_temp_norm = (heat_res - cold_res) * 0.06
        temp_deviation = ti.abs(tile_temp - optimal_temp_norm)
        
        # 容忍范围外的死亡率
        temp_tolerance = (heat_res + cold_res) * 0.012
        temp_mortality = 0.0
        
        if temp_deviation > temp_tolerance:
            excess = temp_deviation - temp_tolerance
            # 根据是太热还是太冷，使用对应的耐受性
            if tile_temp > optimal_temp_norm:
                # 太热：耐热性决定死亡率
                temp_mortality = excess * (11.0 - heat_res) * 0.08
            else:
                # 太冷：耐寒性决定死亡率
                temp_mortality = excess * (11.0 - cold_res) * 0.08
        
        temp_mortality = ti.min(0.60, temp_mortality)
        
        # ========== 2. 湿度/干旱压力死亡率 ==========
        optimal_humidity = 1.0 - drought_res * 0.08
        humidity_deviation = ti.abs(tile_humidity - optimal_humidity)
        humidity_tolerance = 0.12 + drought_res * 0.02
        
        humidity_mortality = 0.0
        if humidity_deviation > humidity_tolerance:
            excess = humidity_deviation - humidity_tolerance
            humidity_mortality = excess * (11.0 - drought_res) * 0.06
        
        humidity_mortality = ti.min(0.40, humidity_mortality)
        
        # ========== 3. 盐度压力死亡率 ==========
        tile_salinity = tile_ocean * 1.0  # 海洋=高盐
        optimal_salinity = salt_res * 0.1
        salinity_deviation = ti.abs(tile_salinity - optimal_salinity)
        
        salinity_mortality = 0.0
        if salinity_deviation > 0.2:
            salinity_mortality = (salinity_deviation - 0.2) * (11.0 - salt_res) * 0.08
        
        salinity_mortality = ti.min(0.50, salinity_mortality)
        
        # ========== 4. 栖息地不匹配死亡率 ==========
        habitat_mortality = 0.0
        is_land_only = land_pref > 0.7 and ocean_pref < 0.2
        is_ocean_only = ocean_pref > 0.7 and land_pref < 0.2
        
        if is_land_only and tile_ocean > 0.5:
            # 陆生物种在海洋：高死亡
            habitat_mortality = 0.60
        elif is_ocean_only and tile_land > 0.5:
            # 海洋物种在陆地：高死亡
            habitat_mortality = 0.60
        
        # ========== 5. 资源竞争死亡率 ==========
        total_pop_tile = 0.0
        for sp in range(S):
            total_pop_tile += pop[sp, i, j]
        
        # 体型影响资源需求
        resource_need = body_size * 0.1 + 0.3
        capacity = tile_resource * 100.0 / resource_need
        saturation = total_pop_tile / (capacity + 1e-6)
        
        resource_mortality = 0.0
        if saturation > 0.6:
            resource_mortality = (saturation - 0.6) * 0.35
        
        resource_mortality = ti.min(0.45, resource_mortality)
        
        # ========== 6. 猎物稀缺死亡率（消费者）==========
        prey_mortality = 0.0
        if trophic >= 2.0:
            prey_density = 0.0
            for sp in range(S):
                prey_trophic = species_traits[sp, 11]
                if prey_trophic < trophic and prey_trophic >= trophic - 1.5:
                    prey_density += pop[sp, i, j]
            
            prey_ratio = prey_density / (total_pop_tile + 1e-6)
            if prey_ratio < 0.15:
                prey_mortality = (0.15 - prey_ratio) * 2.5
            elif prey_ratio < 0.30:
                prey_mortality = (0.30 - prey_ratio) * 0.5
        
        prey_mortality = ti.min(0.55, prey_mortality)
        
        # ========== 7. 低宜居度死亡率 ==========
        suit = suitability[s, i, j]
        suit_mortality = 0.0
        
        if suit < 0.10:
            suit_mortality = 0.65
        elif suit < 0.25:
            suit_mortality = 0.45 - (suit - 0.10) * 2.0
        elif suit < 0.50:
            suit_mortality = (0.50 - suit) * 0.30
        
        # ========== 8. 外部压力死亡率 ==========
        external_pressure = 0.0
        for c in range(C_pressure):
            external_pressure += pressure_overlay[c, i, j]
        external_mortality = ti.min(0.50, external_pressure * 0.12)
        
        # ========== 综合死亡率 ==========
        total_mortality = (
            temp_mortality * 0.22 +
            humidity_mortality * 0.12 +
            salinity_mortality * 0.12 +
            habitat_mortality * 0.15 +
            resource_mortality * 0.15 +
            prey_mortality * 0.10 +
            suit_mortality * 0.10 +
            external_mortality +
            base_mortality
        )
        
        # 时代缩放（保守）
        if era_scaling > 1.5:
            scale_factor = ti.max(0.88, 1.0 / ti.pow(era_scaling, 0.12))
            total_mortality *= scale_factor
        
        result[s, i, j] = ti.max(0.02, ti.min(0.92, total_mortality))


@ti.kernel
def kernel_trait_diffusion(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
):
    """基于特质的扩散计算 - Taichi GPU 并行
    
    【v3.0 修复】加入栖息地连通性检查，防止跨栖息地扩散
    
    【核心规则】
    1. 陆地物种只能向陆地/海岸扩散，不能进入纯海洋
    2. 海洋物种只能向海洋/海岸扩散，不能进入纯陆地
    3. 机动性特质影响扩散速度
    
    Args:
        pop: 种群张量 (S, H, W)
        suitability: 适宜度张量 (S, H, W)
        species_traits: 物种特质 (S, 14)
            [8] 陆地偏好 0-1
            [9] 海洋偏好 0-1
            [10] 海岸偏好 0-1
        env: 环境张量 (C, H, W) - [温度, 湿度, 海拔, 资源, 陆地, 海洋, 海岸]
        new_pop: 扩散后的种群张量 (S, H, W)
        base_rate: 基础扩散率
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C = env.shape[0]
    
    # 阈值
    SUIT_THRESHOLD = 0.18
    SUIT_LOW_THRESHOLD = 0.10
    DENSITY_THRESHOLD = 40.0
    CROWDING_THRESHOLD = 80.0
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        my_suit = suitability[s, i, j]
        
        # 获取物种特质
        mobility = species_traits[s, 7]  # 机动性 1-10
        body_size = species_traits[s, 6]  # 体型（大体型移动慢）
        land_pref = species_traits[s, 8]   # 陆地偏好 0-1
        ocean_pref = species_traits[s, 9]  # 海洋偏好 0-1
        coast_pref = species_traits[s, 10] # 海岸偏好 0-1
        
        # 判断物种类型
        is_terrestrial = land_pref > 0.5 and ocean_pref < 0.4
        is_aquatic = ocean_pref > 0.5 and land_pref < 0.4
        is_amphibious = coast_pref > 0.4 or (land_pref > 0.3 and ocean_pref > 0.3)
        
        # 获取当前地块的栖息地类型
        my_land = env[4, i, j] if C > 4 else 1.0
        my_ocean = env[5, i, j] if C > 5 else 0.0
        my_coast = env[6, i, j] if C > 6 else 0.0
        
        # 机动性调整扩散率
        mobility_factor = 0.5 + mobility * 0.1  # 范围 0.6 ~ 1.5
        size_penalty = 1.0 - (body_size - 5) * 0.03  # 大体型惩罚
        effective_rate = base_rate * mobility_factor * size_penalty
        
        # 计算流入和流出
        outflow = 0.0
        inflow = 0.0
        density_outflow = 0.0
        escape_outflow = 0.0
        
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        any_better = False
        any_lower_density = False
        valid_neighbor_count = 0
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                neighbor_suit = suitability[s, ni, nj]
                neighbor_pop = pop[s, ni, nj]
                gradient = neighbor_suit - my_suit
                density_gradient = current - neighbor_pop
                
                # 【关键】获取邻居地块的栖息地类型
                n_land = env[4, ni, nj] if C > 4 else 1.0
                n_ocean = env[5, ni, nj] if C > 5 else 0.0
                n_coast = env[6, ni, nj] if C > 6 else 0.0
                
                # 【栖息地连通性检查】计算物种是否可以进入该邻居地块
                can_enter = True
                if is_terrestrial and not is_amphibious:
                    if n_ocean > 0.6 and n_coast < 0.3:
                        can_enter = False
                if is_aquatic and not is_amphibious:
                    if n_land > 0.6 and n_coast < 0.3:
                        can_enter = False
                
                # 【Taichi兼容】用条件包裹代替continue
                if can_enter:
                    valid_neighbor_count += 1
                    
                    if neighbor_suit > my_suit:
                        any_better = True
                    if neighbor_pop < current * 0.5:
                        any_lower_density = True
                    
                    # 流出计算
                    if current > 0:
                        # 适宜度梯度扩散
                        if neighbor_suit > SUIT_THRESHOLD:
                            if gradient > 0:
                                rate = effective_rate * (1.0 + gradient * 0.6)
                                outflow += current * rate * 0.25
                            elif gradient > -0.25:
                                rate = effective_rate * 0.4
                                outflow += current * rate * 0.25
                        
                        # 密度驱动扩散
                        if current > DENSITY_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                            if density_gradient > 0:
                                pressure_factor = ti.min(2.5, current / DENSITY_THRESHOLD)
                                rate = effective_rate * 1.8 * pressure_factor * (density_gradient / (current + 1.0))
                                density_outflow += current * rate * 0.25
                        
                        # 极端拥挤强制扩散
                        if current > CROWDING_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                            crowding_rate = effective_rate * 2.5 * (current / CROWDING_THRESHOLD)
                            density_outflow += current * crowding_rate * 0.12
                        
                        # 低宜居度逃逸
                        if neighbor_suit > SUIT_LOW_THRESHOLD and my_suit < 0.15:
                            if gradient > 0:
                                escape_rate = effective_rate * 2.2 * gradient
                                escape_outflow += current * escape_rate * 0.25
                    
                    # 流入计算
                    if neighbor_pop > 0:
                        # 【流入也需要检查】邻居物种能否流入当前地块
                        can_receive = True
                        if is_terrestrial and not is_amphibious:
                            if my_ocean > 0.6 and my_coast < 0.3:
                                can_receive = False
                        if is_aquatic and not is_amphibious:
                            if my_land > 0.6 and my_coast < 0.3:
                                can_receive = False
                        
                        if can_receive:
                            if my_suit > SUIT_THRESHOLD:
                                if gradient < 0:
                                    rate = effective_rate * (1.0 - gradient * 0.6)
                                    inflow += neighbor_pop * rate * 0.25
                                elif gradient < 0.25:
                                    rate = effective_rate * 0.4
                                    inflow += neighbor_pop * rate * 0.25
                            elif my_suit > SUIT_LOW_THRESHOLD:
                                if neighbor_pop > DENSITY_THRESHOLD and current < neighbor_pop * 0.5:
                                    rate = effective_rate * 0.9 * (neighbor_pop / CROWDING_THRESHOLD)
                                    inflow += neighbor_pop * rate * 0.25
        
        # 随机逃逸（只在有有效邻居时）
        random_escape = 0.0
        if current > 0 and valid_neighbor_count > 0:
            if my_suit < 0.15 and not any_better:
                noise = 0.5 + 0.5 * ti.sin(ti.cast(i * 13 + j * 17 + s * 7, ti.f32))
                if noise > 0.55:
                    random_escape = current * effective_rate * 0.18
            elif current > CROWDING_THRESHOLD * 1.5 and not any_lower_density:
                random_escape = current * effective_rate * 0.12
        
        # 限制最大流出（机动性高可以流出更多）
        max_outflow_ratio = 0.50 + mobility * 0.02  # 范围 0.52 ~ 0.70
        total_outflow = outflow + density_outflow + escape_outflow + random_escape
        if current > 0:
            total_outflow = ti.min(total_outflow, current * max_outflow_ratio)
        else:
            total_outflow = 0.0
        
        new_pop[s, i, j] = current - total_outflow + inflow


# ============================================================================
# 预编译所有内核（在主线程中）
# ============================================================================

def _precompile_all_kernels():
    """在模块加载时预编译所有 Taichi 内核
    
    Taichi 内核在首次调用时才会编译，如果首次调用发生在非主线程，
    会触发 "Assertion failure: std::this_thread::get_id() == main_thread_id_" 错误。
    
    通过在模块加载时（主线程）用小数组调用所有内核，可以提前完成编译。
    """
    global _taichi_backend
    
    if _taichi_backend is None:
        logger.warning("[Taichi] 跳过预编译：GPU 后端未初始化")
        return
    
    import numpy as np
    
    # 使用最小的测试数组
    S, H, W = 1, 2, 2
    
    try:
        # 创建测试数组
        pop = np.ones((S, H, W), dtype=np.float32)
        env = np.ones((7, H, W), dtype=np.float32)
        params = np.ones((S, 4), dtype=np.float32)
        prefs = np.ones((S, 6), dtype=np.float32)
        trophic = np.ones((S,), dtype=np.float32)
        pressure = np.zeros((3, H, W), dtype=np.float32)
        result_3d = np.zeros((S, H, W), dtype=np.float32)
        suitability = np.ones((S, H, W), dtype=np.float32)
        capacity = np.ones((H, W), dtype=np.float32)
        habitat_mask = np.ones((S, H, W), dtype=np.float32)
        death_rates = np.zeros((S,), dtype=np.float32)
        migration_rates = np.ones((S,), dtype=np.float32)
        distance_weights = np.ones((S, H, W), dtype=np.float32)
        migration_scores = np.zeros((S, H, W), dtype=np.float32)
        traits = np.ones((S, 14), dtype=np.float32)  # 【修复】提前定义 traits
        scale_arr = np.ones((S,), dtype=np.float32)  # 【新增】缩放因子数组
        
        # 预编译各内核（小数组调用，仅触发编译）
        kernel_mortality(pop, env, params, result_3d, 0, 20.0, 15.0)
        kernel_apply_mortality(pop, result_3d, result_3d)
        kernel_compute_suitability(env, prefs, habitat_mask, result_3d)
        kernel_advanced_diffusion(pop, suitability, result_3d, 0.1)
        kernel_reproduction(pop, suitability, capacity, 0.1, result_3d)
        kernel_competition(pop, suitability, result_3d, 0.1)
        kernel_compute_distance_weights(pop, result_3d, 3.0)
        # kernel_migration_decision 需要 7 个参数
        kernel_migration_decision(
            pop, suitability, distance_weights, death_rates, 
            migration_scores, 0.12, 0.8  # pressure_threshold, saturation_threshold
        )
        if 'kernel_migration_decision_v2' in globals():
            kernel_migration_decision_v2(
                pop, suitability, distance_weights, death_rates,
                death_rates,  # resource_pressure 占位
                suitability,  # prey_density 占位
                trophic,
                traits,  # 【新】species_traits
                env,     # 【新】env
                migration_scores,
                0.12, 0.8, 0.9, 0.35, 0.3, 0.1, 2.0
            )
        kernel_execute_migration(
            pop, migration_scores, distance_weights, 
            traits,  # 【新】species_traits
            env,     # 【新】env
            result_3d, migration_rates, 0.25, 0.01
        )
        kernel_multifactor_mortality(
            pop, env, prefs, params, trophic, pressure, result_3d,
            0.05, 0.3, 0.2, 0.15, 1.0, 1.0
        )
        
        # 【新】预编译特质系统内核
        niche_overlap = np.zeros((S, S), dtype=np.float32)
        local_fitness = np.ones((S, H, W), dtype=np.float32)
        
        kernel_compute_trait_suitability(env, traits, result_3d)
        kernel_compute_local_fitness(suitability, traits, pop, local_fitness)
        kernel_compute_niche_overlap_matrix(traits, niche_overlap)
        kernel_apply_trait_competition(pop, local_fitness, niche_overlap, result_3d, 0.1)
        kernel_trait_mortality(pop, env, traits, suitability, pressure, result_3d, 0.05, 1.0)
        kernel_trait_diffusion(pop, suitability, traits, env, result_3d, 0.1)
        
        # 【v3.1】预编译 v2 内核（带缩放因子）
        kernel_advanced_diffusion_v2(pop, suitability, scale_arr, result_3d, 0.1, 0.05, 15.0, 0.2)
        kernel_trait_diffusion_v2(pop, suitability, traits, env, scale_arr, result_3d, 0.1, 0.05, 15.0, 0.2)
        kernel_reproduction_v2(pop, suitability, capacity, scale_arr, 0.1, result_3d)
        kernel_multifactor_mortality_v2(
            pop, env, prefs, params, trophic, pressure, scale_arr, result_3d,
            0.05, 0.3, 0.2, 0.15, 1.0, 1.0
        )
        kernel_trait_mortality_v2(pop, env, traits, suitability, pressure, scale_arr, result_3d, 0.05, 1.0)
        
        # 同步 Taichi 运行时
        ti.sync()
        
        logger.info("[Taichi] 所有内核预编译完成（含特质系统和v2内核）")
        
    except Exception as e:
        logger.warning(f"[Taichi] 内核预编译失败（将在首次使用时编译）: {e}")




# ============================================================================
# 竞争计算内核 - GPU 加速的亲缘竞争计算
# ============================================================================

@ti.kernel
def kernel_amplify_difference(
    ranks: ti.types.ndarray(dtype=ti.f32, ndim=1),
    result: ti.types.ndarray(dtype=ti.f32, ndim=1),
    power: ti.f32,
    n: ti.i32,
):
    """GPU并行差距放大"""
    for i in range(n):
        centered = (ranks[i] - 0.5) * 2.0
        # Taichi 需要在 if 之前声明变量
        amplified = ti.f32(0.0)
        if centered >= 0:
            amplified = ti.pow(centered, 1.0 / power)
        else:
            amplified = -ti.pow(-centered, power)
        result[i] = (amplified + 1.0) / 2.0


@ti.kernel
def kernel_compute_fitness_1d(
    pop_amp: ti.types.ndarray(dtype=ti.f32, ndim=1),
    survival_amp: ti.types.ndarray(dtype=ti.f32, ndim=1),
    repro_amp: ti.types.ndarray(dtype=ti.f32, ndim=1),
    trophic: ti.types.ndarray(dtype=ti.f32, ndim=1),
    age: ti.types.ndarray(dtype=ti.f32, ndim=1),
    fitness: ti.types.ndarray(dtype=ti.f32, ndim=1),
    n: ti.i32,
):
    """GPU并行计算最终适应度
    
    【v2.2 修复】新分化物种适应性优势：
    - 新物种（年龄<5）获得适应性加成（它们是因为更适应环境才分化出来的）
    - 老物种（年龄>10）受到适应性惩罚（可能已经过时）
    - 种群数量权重降低，避免大种群永远占优
    """
    for i in range(n):
        # 营养级分数
        trophic_score = ti.max(0.2, 1.2 - trophic[i] * 0.25)
        
        # 【修改】降低种群数量权重，提高生存率和繁殖效率权重
        # 这样新物种不会因为数量少就处于劣势
        fit = (
            pop_amp[i] * 0.25 +        # 种群数量权重降低（0.40 → 0.25）
            survival_amp[i] * 0.35 +   # 生存率权重提高（0.30 → 0.35）
            repro_amp[i] * 0.25 +      # 繁殖效率权重提高（0.20 → 0.25）
            trophic_score * 0.15       # 营养级权重提高（0.10 → 0.15）
        )
        
        # 【新增】年龄调节：新物种优势 + 老物种惩罚
        if age[i] <= 2:
            # 刚分化的新物种：显著适应性优势（+25%）
            # 它们是因为更适应当前环境才分化出来的
            fit *= 1.25
        elif age[i] <= 5:
            # 年轻物种：中等优势（+15%）
            fit *= 1.15
        elif age[i] <= 10:
            # 中年物种：轻微优势（+5%）
            fit *= 1.05
        elif age[i] <= 20:
            # 成熟物种：无加成也无惩罚
            pass
        elif age[i] <= 30:
            # 老物种：轻微惩罚
            fit *= 0.95
        else:
            # 非常老的物种：显著惩罚
            fit *= 0.85
        
        fitness[i] = ti.min(1.0, ti.max(0.0, fit))


@ti.kernel
def kernel_build_overlap_matrix_2d(
    overlaps: ti.types.ndarray(dtype=ti.f32, ndim=1),
    overlap_matrix: ti.types.ndarray(dtype=ti.f32, ndim=2),
    n: ti.i32,
):
    """GPU并行构建重叠矩阵"""
    for i, j in ti.ndrange(n, n):
        overlap_matrix[i, j] = (overlaps[i] + overlaps[j]) / 2.0


@ti.kernel
def kernel_build_trophic_mask_2d(
    trophic: ti.types.ndarray(dtype=ti.f32, ndim=1),
    mask: ti.types.ndarray(dtype=ti.f32, ndim=2),
    n: ti.i32,
):
    """GPU并行构建营养级掩码"""
    for i, j in ti.ndrange(n, n):
        ti_rounded = ti.round(trophic[i] * 2.0) / 2.0
        tj_rounded = ti.round(trophic[j] * 2.0) / 2.0
        diff = ti.abs(ti_rounded - tj_rounded)
        mask[i, j] = 1.0 if diff < 0.5 else 0.0


@ti.kernel
def kernel_compute_competition_mods(
    fitness: ti.types.ndarray(dtype=ti.f32, ndim=1),
    kinship: ti.types.ndarray(dtype=ti.i32, ndim=2),
    overlap: ti.types.ndarray(dtype=ti.f32, ndim=2),
    trophic_mask: ti.types.ndarray(dtype=ti.f32, ndim=2),
    repro: ti.types.ndarray(dtype=ti.f32, ndim=1),
    mortality_mods: ti.types.ndarray(dtype=ti.f32, ndim=1),
    repro_mods: ti.types.ndarray(dtype=ti.f32, ndim=1),
    n: ti.i32,
    kin_threshold: ti.i32,
    kin_multiplier: ti.f32,
    nonkin_multiplier: ti.f32,
    disadvantage_threshold: ti.f32,
    winner_reduction: ti.f32,
    loser_penalty_max: ti.f32,
    contested_coef: ti.f32,
):
    """GPU并行计算竞争修正 - 核心内核"""
    for i in range(n):
        winner_bonus_sum = 0.0
        loser_penalty_sum = 0.0
        contested_penalty_sum = 0.0
        nonkin_pressure_sum = 0.0
        
        for j in range(n):
            if i == j:
                continue
            
            # 跳过不同营养级
            if trophic_mask[i, j] < 0.5:
                continue
            
            # 适应度差异
            fitness_diff = fitness[i] - fitness[j]
            
            # 亲缘关系
            is_kin = 1.0 if kinship[i, j] <= kin_threshold else 0.0
            
            # 世代速度因子
            avg_repro = (repro[i] + repro[j]) / 2.0
            gen_speed = 0.6 + avg_repro * 0.08
            
            # 重叠度
            ovlp = overlap[i, j]
            
            # 计算竞争强度
            base_intensity = ovlp * kin_multiplier
            total_intensity = 0.0
            
            # 高重叠（>0.6）
            if ovlp > 0.6:
                kin_bonus = 1.3 if is_kin > 0.5 else 1.0
                total_intensity = base_intensity * kin_bonus * gen_speed
            # 中等重叠（0.3-0.6）
            elif ovlp > 0.3:
                if is_kin > 0.5:
                    total_intensity = base_intensity * gen_speed
                else:
                    # 异属温和竞争
                    temp_intensity = ovlp * nonkin_multiplier * 0.1 * gen_speed
                    fit_sum = fitness[i] + fitness[j] + 0.01
                    nonkin_pressure_sum += temp_intensity * (1.0 - fitness[i] / fit_sum)
                    continue
            else:
                # 低重叠，不竞争
                continue
            
            # 计算胜负
            advantage = ti.abs(fitness_diff)
            
            if fitness_diff > disadvantage_threshold:
                # 我是强者
                bonus = ti.min(winner_reduction, total_intensity * advantage * 0.5)
                winner_bonus_sum += bonus
            elif fitness_diff < -disadvantage_threshold:
                # 我是弱者
                refuge_factor = 1.0 - (1.0 - ovlp) * 0.5
                penalty = ti.min(loser_penalty_max, total_intensity * advantage * 1.0) * refuge_factor
                loser_penalty_sum += penalty
            else:
                # 势均力敌
                contested_penalty_sum += total_intensity * contested_coef
        
        # 汇总修正
        mortality_mods[i] = winner_bonus_sum - loser_penalty_sum - contested_penalty_sum - nonkin_pressure_sum
        repro_mods[i] = winner_bonus_sum * 0.5 - loser_penalty_sum * 0.3


# ============================================================================
# 增强适宜度计算内核 - 实现生态位分化和竞争排斥
# ============================================================================

@ti.kernel
def kernel_enhanced_suitability(
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    habitat_mask: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    # 环境容忍度参数
    temp_tolerance_coef: ti.f32,
    temp_penalty_rate: ti.f32,
    humidity_penalty_rate: ti.f32,
    resource_threshold: ti.f32,
    # 环境通道索引
    temp_idx: ti.i32,
    humidity_idx: ti.i32,
    elevation_idx: ti.i32,
    resource_idx: ti.i32,
    salinity_idx: ti.i32,
    light_idx: ti.i32,
):
    """增强版适宜度计算 - Taichi 并行
    
    【收紧环境容忍度】
    - 温度容忍范围缩小（从40°C→25°C）
    - 温度惩罚加重（超出5°C就归零）
    - 湿度惩罚加重
    - 资源门槛提高
    
    Args:
        env: 环境张量 (C, H, W) - 多通道环境数据
        species_traits: 物种特质 (S, T) - [耐寒性, 耐热性, 耐旱性, 耐盐性, 光照需求, ...]
        habitat_mask: 栖息地掩码 (S, H, W)
        result: 适宜度输出 (S, H, W)
    
    species_traits 格式:
        [0] 耐寒性 (1-10)
        [1] 耐热性 (1-10)
        [2] 耐旱性 (1-10)
        [3] 耐盐性 (1-10)
        [4] 光照需求 (1-10)
        [5] 栖息地类型编码 (0=marine, 1=terrestrial, etc.)
        [6] 专化度 (0-1, 高=专化, 低=泛化)
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        # 硬约束检查
        if habitat_mask[s, i, j] < 0.5:
            result[s, i, j] = 0.0
            continue
        
        # 获取物种特质
        cold_res = species_traits[s, 0]  # 耐寒性 1-10
        heat_res = species_traits[s, 1]  # 耐热性 1-10
        drought_res = species_traits[s, 2]  # 耐旱性 1-10
        salt_res = species_traits[s, 3]  # 耐盐性 1-10
        light_req = species_traits[s, 4]  # 光照需求 1-10
        specialization = species_traits[s, 6]  # 专化度 0-1
        
        # 获取环境参数
        tile_temp = env[temp_idx, i, j]  # 归一化温度 [-1, 1]
        tile_humidity = env[humidity_idx, i, j]  # 湿度 [0, 1]
        tile_elevation = env[elevation_idx, i, j]  # 海拔（归一化）
        tile_resource = env[resource_idx, i, j]  # 资源 [0, 1]
        tile_salinity = env[salinity_idx, i, j]  # 盐度 [0, 1]
        tile_light = env[light_idx, i, j]  # 光照 [0, 1]
        
        # ========== 1. 温度适宜度（收紧版）==========
        # 使用缩小后的系数计算容忍范围
        # 耐寒性影响最低温度：min_temp = 15 - cold_res * temp_tolerance_coef
        # 耐热性影响最高温度：max_temp = 15 + heat_res * temp_tolerance_coef
        # 归一化：假设环境温度 [-30, 50] 映射到 [-1, 1]
        
        # 物种最优温度（基于特质平均）
        optimal_temp_raw = 15.0 + (heat_res - cold_res) * 2.0  # 范围 [-5, 35]
        # 归一化到 [-1, 1]
        optimal_temp = (optimal_temp_raw - 10.0) / 40.0
        
        # 容忍范围（缩小版）
        tolerance_range = (cold_res + heat_res) * temp_tolerance_coef / 80.0  # 归一化后的范围
        
        temp_diff = ti.abs(tile_temp - optimal_temp)
        
        if temp_diff <= tolerance_range:
            temp_score = 1.0
        else:
            # 超出范围，使用加重的惩罚率
            excess = temp_diff - tolerance_range
            temp_score = ti.max(0.0, 1.0 - excess * temp_penalty_rate * 10.0)
        
        # ========== 2. 湿度适宜度（收紧版）==========
        # 耐旱性越高，最佳湿度越低
        optimal_humidity = 1.0 - drought_res * 0.08  # 范围 [0.2, 0.92]
        humidity_diff = ti.abs(tile_humidity - optimal_humidity)
        
        # 加重的湿度惩罚
        humidity_score = ti.max(0.0, 1.0 - humidity_diff * humidity_penalty_rate)
        
        # ========== 3. 盐度适宜度 ==========
        # 耐盐性决定最佳盐度
        optimal_salinity = salt_res * 0.1  # 高耐盐=高盐度偏好
        salinity_diff = ti.abs(tile_salinity - optimal_salinity)
        salinity_score = ti.max(0.0, 1.0 - salinity_diff * 3.0)
        
        # ========== 4. 光照适宜度 ==========
        # 光照需求高的物种需要高光照
        optimal_light = light_req * 0.1
        light_diff = ti.abs(tile_light - optimal_light)
        light_score = ti.max(0.0, 1.0 - light_diff * 2.0)
        
        # ========== 5. 资源适宜度（提高门槛）==========
        resource_score = ti.min(1.0, tile_resource / resource_threshold)
        
        # ========== 6. 深度/海拔惩罚 ==========
        # 深海物种在浅水惩罚，浅水物种在深水惩罚
        elevation_score = 1.0  # 默认满分，具体逻辑由habitat_mask处理
        
        # ========== 7. 综合适宜度 ==========
        base_suitability = (
            temp_score * 0.25 +
            humidity_score * 0.15 +
            salinity_score * 0.15 +
            light_score * 0.10 +
            resource_score * 0.20 +
            elevation_score * 0.15
        )
        
        # ========== 8. 专化度权衡 ==========
        # 泛化物种（specialization < 0.3）：适宜度打折但范围广
        # 专化物种（specialization > 0.7）：适宜度高但范围窄（已由各单项惩罚体现）
        if specialization < 0.3:
            # 泛化物种：基础适宜度打 0.75 折
            generalist_penalty = 0.75 + specialization * 0.25
            base_suitability *= generalist_penalty
        
        # 确保范围并输出
        result[s, i, j] = ti.max(0.0, ti.min(1.0, base_suitability))


@ti.kernel
def kernel_niche_crowding_penalty(
    base_suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    crowding_penalty_per_species: ti.f32,
    max_crowding_penalty: ti.f32,
    trophic_tolerance: ti.f32,
):
    """生态位拥挤惩罚 - 同营养级物种越多，适宜度越低
    
    【核心逻辑】
    竞争排斥原则：同生态位物种不能长期共存
    同地块同营养级物种数量越多，每个物种的有效适宜度越低
    
    Args:
        base_suitability: 基础适宜度 (S, H, W)
        trophic_levels: 各物种营养级 (S,)
        pop: 种群分布 (S, H, W)
        result: 调整后适宜度 (S, H, W)
        crowding_penalty_per_species: 每多一个竞争者的惩罚
        max_crowding_penalty: 最大惩罚比例
        trophic_tolerance: 营养级差异容忍度（差异小于此值视为同营养级）
    """
    S, H, W = base_suitability.shape[0], base_suitability.shape[1], base_suitability.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        base_suit = base_suitability[s, i, j]
        
        if base_suit <= 0.01:
            result[s, i, j] = 0.0
            continue
        
        my_trophic = trophic_levels[s]
        
        # 计算同地块同营养级的竞争者数量
        competitor_count = 0
        competitor_biomass = 0.0
        
        for other in range(S):
            if other == s:
                continue
            
            # 检查是否在同一地块有种群
            if pop[other, i, j] <= 0:
                continue
            
            # 检查是否同营养级
            trophic_diff = ti.abs(trophic_levels[other] - my_trophic)
            if trophic_diff <= trophic_tolerance:
                competitor_count += 1
                competitor_biomass += pop[other, i, j]
        
        # 计算拥挤惩罚
        # 惩罚因子 = 1 / (1 + count * penalty_rate)
        crowding_factor = 1.0 / (1.0 + ti.cast(competitor_count, ti.f32) * crowding_penalty_per_species)
        
        # 应用最大惩罚限制
        crowding_factor = ti.max(1.0 - max_crowding_penalty, crowding_factor)
        
        result[s, i, j] = base_suit * crowding_factor


@ti.kernel
def kernel_resource_split_penalty(
    base_suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    niche_similarity: ti.types.ndarray(dtype=ti.f32, ndim=2),
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    split_coefficient: ti.f32,
    min_split_factor: ti.f32,
):
    """资源分割惩罚 - 生态位重叠物种必须分割资源
    
    【核心逻辑】
    相似物种不能都获得100%资源
    资源被按生态位重叠度分割
    
    Args:
        base_suitability: 基础适宜度 (S, H, W)
        niche_similarity: 物种间生态位相似度矩阵 (S, S)
        pop: 种群分布 (S, H, W)
        result: 调整后适宜度 (S, H, W)
        split_coefficient: 分割系数
        min_split_factor: 最小分割因子（避免完全归零）
    """
    S, H, W = base_suitability.shape[0], base_suitability.shape[1], base_suitability.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        base_suit = base_suitability[s, i, j]
        
        if base_suit <= 0.01:
            result[s, i, j] = 0.0
            continue
        
        # 累计同地块物种的生态位重叠
        total_overlap = 0.0
        
        for other in range(S):
            if other == s:
                continue
            
            # 检查是否在同一地块
            if pop[other, i, j] <= 0:
                continue
            
            # 累加生态位相似度
            total_overlap += niche_similarity[s, other]
        
        # 资源分割因子
        # split_factor = 1 / (1 + total_overlap * coefficient)
        split_factor = 1.0 / (1.0 + total_overlap * split_coefficient)
        split_factor = ti.max(min_split_factor, split_factor)
        
        result[s, i, j] = base_suit * split_factor


@ti.kernel
def kernel_compute_specialization(
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=1),
    trait_count: ti.i32,
):
    """计算物种专化度 - 基于特质分布的集中程度
    
    方差越大 = 越专化（某些特质很高，某些很低）
    方差越小 = 越泛化（所有特质都中等）
    
    Args:
        species_traits: 物种特质矩阵 (S, T) - 前 trait_count 列用于计算
        result: 专化度输出 (S,) - 范围 [0, 1]
        trait_count: 用于计算专化度的特质数量
    """
    S = result.shape[0]
    
    for s in range(S):
        # 计算均值
        mean_val = 0.0
        for t in range(trait_count):
            mean_val += species_traits[s, t]
        mean_val /= ti.cast(trait_count, ti.f32)
        
        # 计算方差
        variance = 0.0
        for t in range(trait_count):
            diff = species_traits[s, t] - mean_val
            variance += diff * diff
        variance /= ti.cast(trait_count, ti.f32)
        
        # 方差 → 专化度（使用指数变换，方差10对应专化度0.8左右）
        specialization = 1.0 - ti.exp(-variance / 8.0)
        result[s] = ti.min(1.0, ti.max(0.0, specialization))


@ti.kernel
def kernel_compute_niche_similarity(
    species_features: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=2),
    feature_weights: ti.types.ndarray(dtype=ti.f32, ndim=1),
):
    """计算物种间生态位相似度矩阵 - 多维特征向量距离
    
    Args:
        species_features: 物种特征矩阵 (S, F) - F维特征向量
        result: 相似度矩阵输出 (S, S)
        feature_weights: 各特征权重 (F,)
    """
    S, F = species_features.shape[0], species_features.shape[1]
    
    for i, j in ti.ndrange(S, S):
        if i == j:
            result[i, j] = 1.0
            continue
        
        # 加权欧氏距离
        weighted_sq_dist = 0.0
        for f in range(F):
            diff = species_features[i, f] - species_features[j, f]
            weighted_sq_dist += feature_weights[f] * diff * diff
        
        distance = ti.sqrt(weighted_sq_dist)
        
        # 高斯核转换为相似度
        similarity = ti.exp(-distance * distance / 0.5)
        result[i, j] = similarity


@ti.kernel
def kernel_historical_adaptation_penalty(
    base_suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    historical_presence: ti.types.ndarray(dtype=ti.f32, ndim=3),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    novelty_penalty: ti.f32,
    adaptation_bonus: ti.f32,
):
    """历史适应惩罚 - 新环境适宜度降低，老环境适宜度提升
    
    Args:
        base_suitability: 基础适宜度 (S, H, W)
        historical_presence: 历史存在记录 (S, H, W) - 0=从未存在, 1=长期存在
        result: 调整后适宜度 (S, H, W)
        novelty_penalty: 新环境惩罚系数 (如 0.8 = 打8折)
        adaptation_bonus: 老环境加成系数 (如 1.1 = 加10%)
    """
    S, H, W = base_suitability.shape[0], base_suitability.shape[1], base_suitability.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        base_suit = base_suitability[s, i, j]
        history = historical_presence[s, i, j]
        
        if base_suit <= 0.01:
            result[s, i, j] = 0.0
            continue
        
        # 根据历史存在调整适宜度
        if history < 0.1:
            # 新环境：惩罚
            adjustment = novelty_penalty
        elif history > 0.8:
            # 老环境：奖励
            adjustment = adaptation_bonus
        else:
            # 中等：线性插值
            adjustment = novelty_penalty + (adaptation_bonus - novelty_penalty) * history
        
        result[s, i, j] = ti.max(0.0, ti.min(1.0, base_suit * adjustment))


@ti.kernel
def kernel_combined_suitability(
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    habitat_mask: ti.types.ndarray(dtype=ti.f32, ndim=3),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    niche_similarity: ti.types.ndarray(dtype=ti.f32, ndim=2),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    # 环境参数（极端收紧版）
    temp_tolerance_coef: ti.f32,      # 温度容忍系数 (1.0=5-10°C范围)
    temp_penalty_rate: ti.f32,        # 温度惩罚率 (0.4=超出2.5°C归零)
    humidity_penalty_rate: ti.f32,    # 湿度惩罚率 (4.0=差0.25归零)
    salinity_penalty_rate: ti.f32,    # 盐度惩罚率 (5.0=差0.2归零)
    light_penalty_rate: ti.f32,       # 光照惩罚率 (3.0=差0.33归零)
    resource_threshold: ti.f32,       # 资源门槛 (0.9=需90%满分)
    # 竞争参数
    crowding_penalty_per_species: ti.f32,  # 每竞争者惩罚 (0.25=2个-50%)
    max_crowding_penalty: ti.f32,          # 最大拥挤惩罚 (0.70=最多-70%)
    trophic_tolerance: ti.f32,             # 营养级容忍度 (0.3=差0.3同级)
    split_coefficient: ti.f32,             # 资源分割系数 (0.5)
    min_split_factor: ti.f32,              # 最小分割因子 (0.2=最低保留20%)
    # 专化度参数
    generalist_threshold: ti.f32,          # 泛化阈值 (0.4)
    generalist_penalty_base: ti.f32,       # 泛化惩罚基础 (0.6=打6折)
    # 权重
    w_temp: ti.f32,
    w_humid: ti.f32,
    w_salt: ti.f32,
    w_light: ti.f32,
    w_res: ti.f32,
    # 环境通道索引
    temp_idx: ti.i32,
    humidity_idx: ti.i32,
    resource_idx: ti.i32,
    salinity_idx: ti.i32,
    light_idx: ti.i32,
):
    """一体化适宜度计算 - 环境 + 拥挤 + 资源分割（极端收紧版）
    
    【设计目标】
    - 温度范围：5-10°C（物种只能在狭窄温度范围生存）
    - 同生态位2个物种：适宜度降50%
    - 泛化物种：适宜度打6折
    
    species_traits 格式:
        [0] 耐寒性 (1-10)
        [1] 耐热性 (1-10)
        [2] 耐旱性 (1-10)
        [3] 耐盐性 (1-10)
        [4] 光照需求 (1-10)
        [5] 专化度 (0-1)
    """
    S, H, W = result.shape[0], result.shape[1], result.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        # ========== 硬约束检查 ==========
        if habitat_mask[s, i, j] < 0.5:
            result[s, i, j] = 0.0
            continue
        
        # ========== 获取物种特质 ==========
        cold_res = species_traits[s, 0]
        heat_res = species_traits[s, 1]
        drought_res = species_traits[s, 2]
        salt_res = species_traits[s, 3]
        light_req = species_traits[s, 4]
        specialization = species_traits[s, 5]
        
        # ========== 获取环境参数 ==========
        tile_temp = env[temp_idx, i, j]
        tile_humidity = env[humidity_idx, i, j]
        tile_resource = env[resource_idx, i, j]
        tile_salinity = env[salinity_idx, i, j]
        tile_light = env[light_idx, i, j]
        
        # ========== 1. 温度适宜度（极端收紧）==========
        # coef=1.0时，10点特质=10°C范围（非常狭窄）
        optimal_temp_raw = 15.0 + (heat_res - cold_res) * 2.0
        optimal_temp = (optimal_temp_raw - 10.0) / 40.0
        tolerance_range = (cold_res + heat_res) * temp_tolerance_coef / 80.0
        temp_diff = ti.abs(tile_temp - optimal_temp)
        
        if temp_diff <= tolerance_range:
            temp_score = 1.0
        else:
            excess = temp_diff - tolerance_range
            temp_score = ti.max(0.0, 1.0 - excess * temp_penalty_rate * 10.0)
        
        # ========== 2. 湿度适宜度（收紧）==========
        optimal_humidity = 1.0 - drought_res * 0.08
        humidity_diff = ti.abs(tile_humidity - optimal_humidity)
        humidity_score = ti.max(0.0, 1.0 - humidity_diff * humidity_penalty_rate)
        
        # ========== 3. 盐度适宜度（收紧）==========
        optimal_salinity = salt_res * 0.1
        salinity_diff = ti.abs(tile_salinity - optimal_salinity)
        salinity_score = ti.max(0.0, 1.0 - salinity_diff * salinity_penalty_rate)
        
        # ========== 4. 光照适宜度（收紧）==========
        optimal_light = light_req * 0.1
        light_diff = ti.abs(tile_light - optimal_light)
        light_score = ti.max(0.0, 1.0 - light_diff * light_penalty_rate)
        
        # ========== 5. 资源适宜度（收紧）==========
        resource_score = ti.min(1.0, tile_resource / resource_threshold)
        
        # ========== 6. 基础适宜度（使用可配置权重）==========
        base_suitability = (
            temp_score * w_temp +
            humidity_score * w_humid +
            salinity_score * w_salt +
            light_score * w_light +
            resource_score * w_res
        )
        
        # ========== 7. 专化度权衡（加强惩罚）==========
        if specialization < generalist_threshold:
            # 泛化惩罚：专化度越低惩罚越重
            penalty_factor = generalist_penalty_base + (1.0 - generalist_penalty_base) * (specialization / generalist_threshold)
            base_suitability *= penalty_factor
        
        # ========== 8. 生态位拥挤惩罚 ==========
        my_trophic = trophic_levels[s]
        competitor_count = 0
        
        for other in range(S):
            if other == s:
                continue
            if pop[other, i, j] <= 0:
                continue
            trophic_diff = ti.abs(trophic_levels[other] - my_trophic)
            if trophic_diff <= trophic_tolerance:
                competitor_count += 1
        
        crowding_factor = 1.0 / (1.0 + ti.cast(competitor_count, ti.f32) * crowding_penalty_per_species)
        crowding_factor = ti.max(1.0 - max_crowding_penalty, crowding_factor)
        
        # ========== 9. 资源分割惩罚 ==========
        total_overlap = 0.0
        for other in range(S):
            if other == s or pop[other, i, j] <= 0:
                continue
            total_overlap += niche_similarity[s, other]
        
        split_factor = 1.0 / (1.0 + total_overlap * split_coefficient)
        split_factor = ti.max(min_split_factor, split_factor)
        
        # ========== 10. 最终适宜度 ==========
        final_suit = base_suitability * crowding_factor * split_factor
        result[s, i, j] = ti.max(0.0, ti.min(1.0, final_suit))


# ============================================================================
# v3.0 世代缩放内核 - 支持 effective_steps 和背景扩散
# ============================================================================

@ti.kernel
def kernel_advanced_diffusion_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    diffusion_scale: ti.types.ndarray(dtype=ti.f32, ndim=1),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
    background_rate: ti.f32,
    density_threshold: ti.f32,
    escape_threshold: ti.f32,
):
    """带世代缩放和背景扩散的高级扩散 - Taichi GPU 并行
    
    【v3.1 修改】
    1. diffusion_scale 已在 Python 层预计算（带上限和缓冲）
    2. 背景扩散：即使没有梯度/低密度，也以 background_rate 的比例输出
    3. 降低密度阈值：更容易触发密度驱动扩散
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    # 阈值
    SUIT_THRESHOLD = 0.18
    SUIT_LOW_THRESHOLD = 0.08
    CROWDING_THRESHOLD = 60.0
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        my_suit = suitability[s, i, j]
        scale = diffusion_scale[s]  # 已预处理的缩放因子（1.0 ~ 2.5）
        
        # 直接使用预计算的缩放因子
        scaled_rate = base_rate * scale
        
        outflow = 0.0
        inflow = 0.0
        density_outflow = 0.0
        escape_outflow = 0.0
        background_outflow = 0.0
        
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        any_better_neighbor = False
        any_lower_density_neighbor = False
        valid_neighbors = 0
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                neighbor_suit = suitability[s, ni, nj]
                neighbor_pop = pop[s, ni, nj]
                valid_neighbors += 1
                
                if neighbor_suit > my_suit:
                    any_better_neighbor = True
                if neighbor_pop < current * 0.5:
                    any_lower_density_neighbor = True
                
                gradient = neighbor_suit - my_suit
                density_gradient = current - neighbor_pop
                
                # === 流出计算 ===
                if current > 0:
                    # 【机制1】适宜度梯度扩散
                    if neighbor_suit > SUIT_THRESHOLD:
                        if gradient > 0:
                            rate = scaled_rate * (1.0 + gradient * 0.6)
                            outflow += current * rate * 0.25
                        elif gradient > -0.25:
                            rate = scaled_rate * 0.45
                            outflow += current * rate * 0.25
                    
                    # 【机制2】密度压力扩散（降低阈值）
                    if current > density_threshold and neighbor_suit > SUIT_LOW_THRESHOLD:
                        if density_gradient > 0:
                            pressure_factor = ti.min(2.5, current / density_threshold)
                            rate = scaled_rate * 1.8 * pressure_factor * (density_gradient / (current + 1.0))
                            density_outflow += current * rate * 0.25
                    
                    # 【机制2b】极端拥挤强制扩散
                    if current > CROWDING_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                        crowding_rate = scaled_rate * 2.5 * (current / CROWDING_THRESHOLD)
                        density_outflow += current * crowding_rate * 0.12
                    
                    # 【机制3】低宜居度逃逸
                    if neighbor_suit > SUIT_LOW_THRESHOLD and my_suit < escape_threshold:
                        if gradient > 0:
                            escape_rate = scaled_rate * 2.5 * gradient
                            escape_outflow += current * escape_rate * 0.25
                    
                    # 【机制4 - 新增】背景扩散（即使梯度为零）
                    if neighbor_suit > SUIT_LOW_THRESHOLD:
                        background_outflow += current * background_rate * 0.25
                
                # === 流入计算 ===
                if neighbor_pop > 0:
                    neighbor_scale = diffusion_scale[s]  # 同物种，使用预计算的缩放
                    neighbor_scaled = base_rate * neighbor_scale
                    
                    if my_suit > SUIT_THRESHOLD:
                        if gradient < 0:
                            rate = neighbor_scaled * (1.0 - gradient * 0.6)
                            inflow += neighbor_pop * rate * 0.25
                        elif gradient < 0.25:
                            rate = neighbor_scaled * 0.45
                            inflow += neighbor_pop * rate * 0.25
                    elif my_suit > SUIT_LOW_THRESHOLD:
                        if neighbor_pop > density_threshold and current < neighbor_pop * 0.5:
                            rate = neighbor_scaled * 0.9 * (neighbor_pop / CROWDING_THRESHOLD)
                            inflow += neighbor_pop * rate * 0.25
                        # 背景流入
                        inflow += neighbor_pop * background_rate * 0.15
        
        # 随机逃逸
        random_escape = 0.0
        if current > 0:
            if my_suit < escape_threshold and not any_better_neighbor and valid_neighbors > 0:
                noise = 0.5 + 0.5 * ti.sin(ti.cast(i * 13 + j * 17 + s * 7, ti.f32))
                if noise > 0.55:
                    random_escape = current * scaled_rate * 0.18
            elif current > CROWDING_THRESHOLD * 1.5 and not any_lower_density_neighbor:
                random_escape = current * scaled_rate * 0.12
        
        # 限制最大流出（使用预计算的缩放，已带上限）
        max_outflow_ratio = ti.min(0.70, 0.50 + 0.08 * scale)  # scale 已是 1.0~2.5
        total_outflow = outflow + density_outflow + escape_outflow + background_outflow + random_escape
        if current > 0:
            total_outflow = ti.min(total_outflow, current * max_outflow_ratio)
        else:
            total_outflow = 0.0
        
        new_pop[s, i, j] = current - total_outflow + inflow


@ti.kernel
def kernel_trait_diffusion_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    diffusion_scale: ti.types.ndarray(dtype=ti.f32, ndim=1),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
    background_rate: ti.f32,
    density_threshold: ti.f32,
    escape_threshold: ti.f32,
):
    """基于特质的扩散计算 v2 - 使用预计算的 diffusion_scale"""
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C = env.shape[0]
    
    SUIT_THRESHOLD = 0.16
    SUIT_LOW_THRESHOLD = 0.08
    CROWDING_THRESHOLD = 50.0
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        my_suit = suitability[s, i, j]
        scale = diffusion_scale[s]  # 预计算的缩放因子（1.0 ~ 2.5）
        
        # 获取物种特质
        mobility = species_traits[s, 7]
        body_size = species_traits[s, 6]
        land_pref = species_traits[s, 8]
        ocean_pref = species_traits[s, 9]
        coast_pref = species_traits[s, 10]
        
        # 判断物种类型
        is_terrestrial = land_pref > 0.5 and ocean_pref < 0.4
        is_aquatic = ocean_pref > 0.5 and land_pref < 0.4
        is_amphibious = coast_pref > 0.4 or (land_pref > 0.3 and ocean_pref > 0.3)
        
        # 当前地块栖息地类型
        my_land = env[4, i, j] if C > 4 else 1.0
        my_ocean = env[5, i, j] if C > 5 else 0.0
        
        # 机动性调整扩散率 + 使用预计算的缩放
        mobility_factor = 0.6 + mobility * 0.12
        size_penalty = 1.0 - (body_size - 5) * 0.025
        effective_rate = base_rate * mobility_factor * size_penalty * scale
        
        outflow = 0.0
        inflow = 0.0
        density_outflow = 0.0
        escape_outflow = 0.0
        background_outflow = 0.0
        
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        any_better = False
        any_lower_density = False
        valid_neighbors = 0
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                neighbor_suit = suitability[s, ni, nj]
                neighbor_pop = pop[s, ni, nj]
                gradient = neighbor_suit - my_suit
                density_gradient = current - neighbor_pop
                
                # 获取邻居栖息地类型
                n_land = env[4, ni, nj] if C > 4 else 1.0
                n_ocean = env[5, ni, nj] if C > 5 else 0.0
                n_coast = env[6, ni, nj] if C > 6 else 0.0
                
                # 栖息地连通性检查（衰减式）
                habitat_factor = 1.0
                if is_terrestrial and not is_amphibious:
                    if n_ocean > 0.6 and n_coast < 0.3:
                        habitat_factor = 0.3  # 衰减而非完全阻止
                if is_aquatic and not is_amphibious:
                    if n_land > 0.6 and n_coast < 0.3:
                        habitat_factor = 0.3
                
                if habitat_factor > 0.1:
                    valid_neighbors += 1
                    
                    if neighbor_suit > my_suit:
                        any_better = True
                    if neighbor_pop < current * 0.5:
                        any_lower_density = True
                    
                    # 流出计算
                    if current > 0:
                        # 适宜度梯度扩散
                        if neighbor_suit > SUIT_THRESHOLD:
                            if gradient > 0:
                                rate = effective_rate * (1.0 + gradient * 0.7) * habitat_factor
                                outflow += current * rate * 0.25
                            elif gradient > -0.22:
                                rate = effective_rate * 0.45 * habitat_factor
                                outflow += current * rate * 0.25
                        
                        # 密度驱动扩散
                        if current > density_threshold and neighbor_suit > SUIT_LOW_THRESHOLD:
                            if density_gradient > 0:
                                pressure_factor = ti.min(3.0, current / density_threshold)
                                rate = effective_rate * 2.0 * pressure_factor * (density_gradient / (current + 1.0)) * habitat_factor
                                density_outflow += current * rate * 0.25
                        
                        # 极端拥挤强制扩散
                        if current > CROWDING_THRESHOLD and neighbor_suit > SUIT_LOW_THRESHOLD:
                            crowding_rate = effective_rate * 3.0 * (current / CROWDING_THRESHOLD) * habitat_factor
                            density_outflow += current * crowding_rate * 0.10
                        
                        # 低宜居度逃逸
                        if neighbor_suit > SUIT_LOW_THRESHOLD and my_suit < escape_threshold:
                            if gradient > 0:
                                escape_rate = effective_rate * 2.8 * gradient * habitat_factor
                                escape_outflow += current * escape_rate * 0.25
                        
                        # 背景扩散
                        if neighbor_suit > SUIT_LOW_THRESHOLD:
                            background_outflow += current * background_rate * habitat_factor * 0.25
                    
                    # 流入计算
                    if neighbor_pop > 0:
                        can_receive = True
                        receive_factor = 1.0
                        if is_terrestrial and not is_amphibious:
                            if my_ocean > 0.6:
                                receive_factor = 0.3
                        if is_aquatic and not is_amphibious:
                            if my_land > 0.6:
                                receive_factor = 0.3
                        
                        if receive_factor > 0.1:
                            if my_suit > SUIT_THRESHOLD:
                                if gradient < 0:
                                    rate = effective_rate * (1.0 - gradient * 0.7) * receive_factor
                                    inflow += neighbor_pop * rate * 0.25
                                elif gradient < 0.22:
                                    rate = effective_rate * 0.45 * receive_factor
                                    inflow += neighbor_pop * rate * 0.25
                            elif my_suit > SUIT_LOW_THRESHOLD:
                                if neighbor_pop > density_threshold and current < neighbor_pop * 0.5:
                                    rate = effective_rate * 1.0 * (neighbor_pop / CROWDING_THRESHOLD) * receive_factor
                                    inflow += neighbor_pop * rate * 0.25
                                inflow += neighbor_pop * background_rate * receive_factor * 0.15
        
        # 随机逃逸
        random_escape = 0.0
        if current > 0 and valid_neighbors > 0:
            if my_suit < escape_threshold and not any_better:
                noise = 0.5 + 0.5 * ti.sin(ti.cast(i * 13 + j * 17 + s * 7, ti.f32))
                if noise > 0.50:
                    random_escape = current * effective_rate * 0.20
            elif current > CROWDING_THRESHOLD * 1.5 and not any_lower_density:
                random_escape = current * effective_rate * 0.15
        
        # 限制最大流出（使用预计算的 scale，已带上限）
        max_outflow_ratio = ti.min(0.70, 0.48 + mobility * 0.02 + scale * 0.05)
        total_outflow = outflow + density_outflow + escape_outflow + background_outflow + random_escape
        if current > 0:
            total_outflow = ti.min(total_outflow, current * max_outflow_ratio)
        else:
            total_outflow = 0.0
        
        new_pop[s, i, j] = current - total_outflow + inflow


@ti.kernel
def kernel_reproduction_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    fitness: ti.types.ndarray(dtype=ti.f32, ndim=3),
    capacity: ti.types.ndarray(dtype=ti.f32, ndim=2),
    birth_scale: ti.types.ndarray(dtype=ti.f32, ndim=1),
    birth_rate: ti.f32,
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
):
    """繁殖计算 v2 - 使用预计算的 birth_scale
    
    【v3.1】birth_scale 已在 Python 层预计算（带上限、压力折扣、容量归一）
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    REPRO_MIN_SUIT = 0.08
    REPRO_LOW_SUIT = 0.22
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] > 0:
            total_pop = 0.0
            for sp in range(S):
                total_pop += pop[sp, i, j]
            
            cap = capacity[i, j]
            suit = fitness[s, i, j]
            scale = birth_scale[s]  # 预计算的缩放因子（1.0 ~ 3.0，已含压力折扣）
            
            if cap > 0 and total_pop > 0:
                crowding = ti.min(1.0, total_pop / cap)
                
                # 宜居度繁殖调节因子
                suit_factor = 1.0
                if suit < REPRO_MIN_SUIT:
                    suit_factor = 0.03
                elif suit < REPRO_LOW_SUIT:
                    suit_factor = 0.03 + (suit - REPRO_MIN_SUIT) / (REPRO_LOW_SUIT - REPRO_MIN_SUIT) * 0.67
                else:
                    suit_factor = ti.min(1.0, suit * 1.25)
                
                # 【v3.1】直接使用预计算的 birth_scale
                effective_rate = birth_rate * suit_factor * (1.0 - crowding) * scale
                
                # 高宜居度+低拥挤时允许更高增长（但限制幅度）
                if suit > 0.6 and crowding < 0.3:
                    effective_rate *= 1.2
                
                result[s, i, j] = pop[s, i, j] * (1.0 + effective_rate)
            else:
                result[s, i, j] = pop[s, i, j]
        else:
            result[s, i, j] = 0.0


@ti.kernel
def kernel_multifactor_mortality_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_prefs: ti.types.ndarray(dtype=ti.f32, ndim=2),
    species_params: ti.types.ndarray(dtype=ti.f32, ndim=2),
    trophic_levels: ti.types.ndarray(dtype=ti.f32, ndim=1),
    pressure_overlay: ti.types.ndarray(dtype=ti.f32, ndim=3),
    mortality_scale: ti.types.ndarray(dtype=ti.f32, ndim=1),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_mortality: ti.f32,
    temp_weight: ti.f32,
    competition_weight: ti.f32,
    resource_weight: ti.f32,
    capacity_multiplier: ti.f32,
    era_scaling: ti.f32,
):
    """多因子死亡率计算 v2 - 使用预计算的 mortality_scale
    
    【v3.1】mortality_scale 已在 Python 层预计算（带上限和缓冲）
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C_env = env.shape[0]
    C_pressure = pressure_overlay.shape[0]
    
    SUIT_LOW_THRESHOLD = 0.22
    SUIT_CRITICAL_THRESHOLD = 0.10
    SUIT_DEATH_WEIGHT = 0.38
    HABITAT_MISMATCH_PENALTY = 0.55
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] <= 0:
            result[s, i, j] = 0.0
            continue
        
        scale = mortality_scale[s]  # 预计算的缩放因子（1.0 ~ 2.5）
        
        # === 1. 温度死亡率 ===
        temp = env[0, i, j]
        temp_pref = species_prefs[s, 0] * 50.0
        temp_deviation = ti.abs(temp - temp_pref)
        temp_tolerance = 15.0
        if species_params.shape[1] >= 2:
            temp_tolerance = ti.max(5.0, species_params[s, 1])
        temp_mortality = 1.0 - ti.exp(-temp_deviation / temp_tolerance)
        temp_mortality = ti.max(0.01, ti.min(0.8, temp_mortality))
        
        # === 2. 湿度死亡率 ===
        humidity = env[1, i, j] if C_env > 1 else 0.5
        humidity_pref = species_prefs[s, 1]
        humidity_deviation = ti.abs(humidity - humidity_pref)
        humidity_mortality = ti.min(0.4, humidity_deviation * 0.5)
        
        # === 3. 竞争死亡率 ===
        total_pop_tile = 0.0
        for sp in range(S):
            total_pop_tile += pop[sp, i, j]
        my_pop = ti.max(pop[s, i, j], 1e-6)
        competitor_pop = total_pop_tile - pop[s, i, j]
        competition_ratio = competitor_pop / (my_pop + 100.0)
        competition_mortality = ti.min(0.35, competition_ratio * 0.12)
        
        # === 4. 资源死亡率 ===
        resources = env[3, i, j] if C_env > 3 else 100.0
        capacity = resources * capacity_multiplier
        saturation = total_pop_tile / (capacity + 1e-6)
        resource_mortality = ti.max(0.0, ti.min(0.45, (saturation - 0.5) * 0.45))
        
        # === 5. 营养级死亡率 ===
        my_trophic = trophic_levels[s]
        prey_scarcity_mortality = 0.0
        if my_trophic >= 2.0:
            prey_density = 0.0
            for sp in range(S):
                prey_trophic = trophic_levels[sp]
                if prey_trophic < my_trophic and prey_trophic >= my_trophic - 1.5:
                    prey_density += pop[sp, i, j]
            prey_density_norm = prey_density / (total_pop_tile + 1e-6)
            if prey_density_norm < 0.20:
                prey_scarcity_mortality = (0.20 - prey_density_norm) * 1.6 + 0.12
            else:
                prey_scarcity_mortality = (1.0 - prey_density_norm) * 0.15
        
        # === 6. 外部压力死亡率 ===
        external_pressure = 0.0
        for c in range(C_pressure):
            external_pressure += pressure_overlay[c, i, j]
        external_mortality = ti.min(0.5, external_pressure * 0.1)
        
        # === 7. 宜居度死亡率（计算简化版）===
        temp_diff = ti.abs(env[0, i, j] - species_prefs[s, 0])
        temp_match = ti.max(0.0, 1.0 - temp_diff * 2.0)
        humidity_match = ti.max(0.0, 1.0 - humidity_deviation * 2.0)
        habitat_match = 0.5
        if C_env >= 7:
            habitat_match = (
                env[4, i, j] * species_prefs[s, 4] +
                env[5, i, j] * species_prefs[s, 5] +
                env[6, i, j] * species_prefs[s, 6]
            )
        suitability = temp_match * 0.35 + humidity_match * 0.25 + habitat_match * 0.40
        suitability = ti.max(0.0, ti.min(1.0, suitability))
        
        suit_mortality = 0.0
        if suitability < SUIT_CRITICAL_THRESHOLD:
            suit_mortality = 0.75
        elif suitability < SUIT_LOW_THRESHOLD:
            suit_mortality = 0.55 - (suitability - SUIT_CRITICAL_THRESHOLD) / (SUIT_LOW_THRESHOLD - SUIT_CRITICAL_THRESHOLD) * 0.40
        else:
            suit_mortality = (1.0 - suitability) * 0.10
        
        # === 8. 栖息地不匹配死亡率 ===
        habitat_mismatch_mortality = 0.0
        if C_env >= 6 and species_prefs.shape[1] >= 6:
            is_land = env[4, i, j] > 0.5
            is_sea = env[5, i, j] > 0.5
            land_pref = species_prefs[s, 4]
            sea_pref = species_prefs[s, 5]
            if is_sea and land_pref > sea_pref + 0.3:
                habitat_mismatch_mortality = HABITAT_MISMATCH_PENALTY
            elif is_land and sea_pref > land_pref + 0.3:
                habitat_mismatch_mortality = HABITAT_MISMATCH_PENALTY
        
        # === 综合死亡率 ===
        total_mortality = (
            temp_mortality * temp_weight +
            humidity_mortality * 0.1 +
            competition_mortality * competition_weight +
            resource_mortality * resource_weight +
            prey_scarcity_mortality +
            external_mortality +
            suit_mortality * SUIT_DEATH_WEIGHT +
            habitat_mismatch_mortality +
            base_mortality
        )
        
        # 【v3.1】世代缩放：使用预计算的 mortality_scale
        # 只在不适环境下应用缩放，避免过度杀伤
        if suitability < 0.3 or habitat_mismatch_mortality > 0:
            # scale 已是 1.0~2.5，再做温和放大
            gen_death_factor = ti.min(1.6, 1.0 + (scale - 1.0) * 0.3)
            total_mortality *= gen_death_factor
        
        # 时代缩放
        if era_scaling > 1.5:
            scale_factor = ti.max(0.82, 1.0 / ti.pow(era_scaling, 0.15))
            total_mortality *= scale_factor
        
        result[s, i, j] = ti.max(0.02, ti.min(0.95, total_mortality))


@ti.kernel
def kernel_trait_mortality_v2(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    env: ti.types.ndarray(dtype=ti.f32, ndim=3),
    species_traits: ti.types.ndarray(dtype=ti.f32, ndim=2),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    pressure_overlay: ti.types.ndarray(dtype=ti.f32, ndim=3),
    mortality_scale: ti.types.ndarray(dtype=ti.f32, ndim=1),
    result: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_mortality: ti.f32,
    era_scaling: ti.f32,
):
    """基于特质的精确死亡率计算 v2 - 使用预计算的 mortality_scale
    
    【v3.1】mortality_scale 已在 Python 层预计算（带上限和缓冲）
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    C_env = env.shape[0]
    C_pressure = pressure_overlay.shape[0]
    
    SUIT_LOW = 0.22
    SUIT_CRITICAL = 0.10
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] <= 0:
            result[s, i, j] = 0.0
            continue
        
        suit = suitability[s, i, j]
        scale = mortality_scale[s]  # 预计算的缩放因子（1.0 ~ 2.5）
        
        # 获取物种特质
        heat_res = species_traits[s, 0]
        cold_res = species_traits[s, 1]
        drought_res = species_traits[s, 2]
        body_size = species_traits[s, 6]
        land_pref = species_traits[s, 8]
        ocean_pref = species_traits[s, 9]
        
        # === 1. 温度死亡率（基于耐受特质）===
        temp = env[0, i, j]
        # 根据耐热/耐寒特质计算最适温度
        optimal_temp = (heat_res - cold_res) * 5.0  # 范围 -50 到 +50
        temp_range = (heat_res + cold_res) * 3.0 + 10.0  # 耐受范围
        temp_dev = ti.abs(temp * 50.0 - optimal_temp)  # 转换到相同尺度
        temp_mortality = ti.min(0.7, ti.max(0.0, (temp_dev - temp_range) / 30.0))
        
        # === 2. 湿度死亡率 ===
        humidity = env[1, i, j] if C_env > 1 else 0.5
        optimal_humidity = 1.0 - drought_res * 0.08
        humidity_mortality = ti.min(0.4, ti.abs(humidity - optimal_humidity) * 0.6)
        
        # === 3. 竞争死亡率（体型影响）===
        total_pop = 0.0
        for sp in range(S):
            total_pop += pop[sp, i, j]
        my_pop = pop[s, i, j]
        competitor_pop = total_pop - my_pop
        # 大体型竞争优势
        size_advantage = 1.0 - (body_size - 5.0) * 0.05
        competition_mortality = ti.min(0.35, competitor_pop / (my_pop + 100.0) * 0.12 * size_advantage)
        
        # === 4. 资源死亡率 ===
        resources = env[3, i, j] if C_env > 3 else 100.0
        capacity = resources * 100.0
        saturation = total_pop / (capacity + 1e-6)
        resource_mortality = ti.max(0.0, ti.min(0.45, (saturation - 0.5) * 0.45))
        
        # === 5. 外部压力 ===
        external_mortality = 0.0
        for c in range(C_pressure):
            external_mortality += pressure_overlay[c, i, j] * 0.1
        external_mortality = ti.min(0.5, external_mortality)
        
        # === 6. 宜居度死亡率 ===
        suit_mortality = 0.0
        if suit < SUIT_CRITICAL:
            suit_mortality = 0.75
        elif suit < SUIT_LOW:
            suit_mortality = 0.55 - (suit - SUIT_CRITICAL) / (SUIT_LOW - SUIT_CRITICAL) * 0.40
        else:
            suit_mortality = (1.0 - suit) * 0.10
        
        # === 7. 栖息地不匹配 ===
        habitat_mortality = 0.0
        if C_env >= 6:
            is_land = env[4, i, j] > 0.5
            is_sea = env[5, i, j] > 0.5
            if is_sea and land_pref > ocean_pref + 0.3:
                habitat_mortality = 0.55
            elif is_land and ocean_pref > land_pref + 0.3:
                habitat_mortality = 0.55
        
        # === 综合死亡率 ===
        total_mortality = (
            temp_mortality * 0.25 +
            humidity_mortality * 0.10 +
            competition_mortality * 0.20 +
            resource_mortality * 0.20 +
            external_mortality +
            suit_mortality * 0.35 +
            habitat_mortality +
            base_mortality
        )
        
        # 【v3.1】世代缩放：使用预计算的 mortality_scale
        # 只在不适环境下应用缩放
        if suit < 0.25 or habitat_mortality > 0:
            # scale 已是 1.0~2.5，再做温和放大
            gen_factor = ti.min(1.6, 1.0 + (scale - 1.0) * 0.35)
            total_mortality *= gen_factor
        
        # 时代缩放
        if era_scaling > 1.5:
            scale_factor = ti.max(0.80, 1.0 / ti.pow(era_scaling, 0.15))
            total_mortality *= scale_factor
        
        result[s, i, j] = ti.max(0.02, ti.min(0.95, total_mortality))

# 在模块加载时预编译
_precompile_all_kernels()
