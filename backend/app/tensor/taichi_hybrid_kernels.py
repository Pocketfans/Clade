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
    """繁殖计算 - Taichi 并行"""
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] > 0:
            total_pop = 0.0
            for sp in range(S):
                total_pop += pop[sp, i, j]
            
            cap = capacity[i, j]
            if cap > 0 and total_pop > 0:
                crowding = ti.min(1.0, total_pop / cap)
                effective_rate = birth_rate * fitness[s, i, j] * (1.0 - crowding)
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
    """批量计算所有物种的迁徙决策分数 - Taichi 并行 (v2.1 修复版)
    
    【v2.1核心修复】只有与已有种群相邻的空地块才能获得迁徙分数
    这确保物种是逐步扩散的，而不是跳跃到任何位置
    
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
    
    for s, i, j in ti.ndrange(S, H, W):
        # 默认分数为0
        migration_scores[s, i, j] = 0.0
        
        # 当前地块已有种群，不需要迁入
        if pop[s, i, j] > 0:
            pass  # 分数保持0
        # 适宜度太低的地块不接收迁徙（硬约束）
        elif suitability[s, i, j] < 0.25:
            pass  # 分数保持0
        else:
            # 【v2.1核心修复】检查是否与已有种群相邻（4邻域）
            adj_count = 0
            if i > 0:
                if pop[s, i - 1, j] > 0:
                    adj_count += 1
            if i < H - 1:
                if pop[s, i + 1, j] > 0:
                    adj_count += 1
            if j > 0:
                if pop[s, i, j - 1] > 0:
                    adj_count += 1
            if j < W - 1:
                if pop[s, i, j + 1] > 0:
                    adj_count += 1
            
            # 只有与已有种群相邻的地块才能获得迁徙分数
            if adj_count > 0:
                death_rate = death_rates[s]
                
                # 基础分数：参考 config.py 中 migration_suitability_bias = 0.6
                base_score = suitability[s, i, j] * 0.6 + distance_weights[s, i, j] * 0.4
                
                # 压力驱动迁徙 - 死亡率高时更愿意迁移
                if death_rate > pressure_threshold:
                    pressure_boost = ti.min(0.5, (death_rate - pressure_threshold) * 2.0)
                    base_score = suitability[s, i, j] * (0.6 - pressure_boost * 0.1) + distance_weights[s, i, j] * (0.4 + pressure_boost * 0.1)
                    base_score *= (1.0 + pressure_boost * 0.5)
                
                # 添加随机扰动（用格子坐标模拟）
                noise = 0.9 + 0.2 * ti.sin(ti.cast(i * 17 + j * 31 + s * 7, ti.f32))
                migration_scores[s, i, j] = base_score * noise


@ti.kernel
def kernel_execute_migration(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    migration_scores: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    migration_rates: ti.types.ndarray(dtype=ti.f32, ndim=1),
    score_threshold: ti.f32,
):
    """执行迁徙 - Taichi 并行
    
    【v2.1修复】添加相邻性检查：物种只能向已有种群相邻的空地块迁徙
    这样物种扩散是逐步的，不会一回合扩散到全世界
    
    Args:
        pop: 当前种群张量 (S, H, W)
        migration_scores: 迁徙分数张量 (S, H, W)
        new_pop: 迁徙后的种群张量 (S, H, W)
        migration_rates: 每个物种的迁徙比例 (S,)
        score_threshold: 分数阈值，低于此值不迁徙
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    for s in range(S):
        # 第一遍：计算该物种的总种群
        total_pop = 0.0
        for i, j in ti.ndrange(H, W):
            total_pop += pop[s, i, j]
        
        # 第二遍：计算只有相邻已有种群的空地块的总迁徙分数
        # 【v2.1核心修复】只有与已有种群相邻的空地块才能接收迁徙
        total_score = 0.0
        for i, j in ti.ndrange(H, W):
            # 必须是空地块且分数足够
            if pop[s, i, j] <= 0 and migration_scores[s, i, j] > score_threshold:
                # 检查是否与已有种群相邻（4邻域）- 用整数计数
                adj_count = 0
                if i > 0:
                    if pop[s, i - 1, j] > 0:
                        adj_count += 1
                if i < H - 1:
                    if pop[s, i + 1, j] > 0:
                        adj_count += 1
                if j > 0:
                    if pop[s, i, j - 1] > 0:
                        adj_count += 1
                if j < W - 1:
                    if pop[s, i, j + 1] > 0:
                        adj_count += 1
                
                # 只有相邻有种群的空地块才计入迁徙分数
                if adj_count > 0:
                    total_score += migration_scores[s, i, j]
        
        # 迁徙量（只迁出一部分种群）
        migrate_amount = total_pop * migration_rates[s]
        
        # 第三遍：按分数比例分配迁徙种群
        for i, j in ti.ndrange(H, W):
            if pop[s, i, j] > 0:
                # 原有种群保留部分
                new_pop[s, i, j] = pop[s, i, j] * (1.0 - migration_rates[s])
            else:
                # 空地块：检查是否可以接收迁入
                new_pop[s, i, j] = 0.0
                
                # 只向相邻已有种群的空地块迁入
                if total_score > 0 and migration_scores[s, i, j] > score_threshold:
                    # 检查相邻性
                    adj_count = 0
                    if i > 0:
                        if pop[s, i - 1, j] > 0:
                            adj_count += 1
                    if i < H - 1:
                        if pop[s, i + 1, j] > 0:
                            adj_count += 1
                    if j > 0:
                        if pop[s, i, j - 1] > 0:
                            adj_count += 1
                    if j < W - 1:
                        if pop[s, i, j + 1] > 0:
                            adj_count += 1
                    
                    # 分配迁入种群（只到相邻空地块）
                    if adj_count > 0:
                        score_ratio = migration_scores[s, i, j] / total_score
                        new_pop[s, i, j] = migrate_amount * score_ratio


@ti.kernel
def kernel_advanced_diffusion(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
):
    """带适宜度引导的高级扩散 - Taichi 并行
    
    种群会优先向适宜度更高的地块扩散。
    【v2.1】参考 config.py: suitability_cutoff = 0.25
    只有适宜度足够高（>0.25）才允许扩散进入！
    
    Args:
        pop: 种群张量 (S, H, W)
        suitability: 适宜度张量 (S, H, W)
        new_pop: 扩散后的种群张量 (S, H, W)
        base_rate: 基础扩散率
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    # 适宜度阈值：低于此值不允许扩散进入
    # 参考 config.py: suitability_cutoff = 0.25
    SUIT_THRESHOLD = 0.25
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        my_suit = suitability[s, i, j]
        
        # 计算流入和流出
        outflow = 0.0
        inflow = 0.0
        
        # 四个邻居方向
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                neighbor_suit = suitability[s, ni, nj]
                neighbor_pop = pop[s, ni, nj]
                
                # 适宜度梯度决定扩散方向和强度
                gradient = neighbor_suit - my_suit
                
                # === 流出计算：当前地块有种群，且邻居适宜度>阈值 ===
                if current > 0 and neighbor_suit > SUIT_THRESHOLD:
                    if gradient > 0:
                        # 向高适宜度流出（种群被吸引到更好的地方）
                        rate = base_rate * (1.0 + gradient * 0.5)
                        outflow += current * rate * 0.25
                    elif gradient > -0.3:
                        # 邻居适宜度稍低但仍可接受，少量扩散
                        rate = base_rate * 0.3
                        outflow += current * rate * 0.25
                
                # === 流入计算：邻居有种群，且我的适宜度>阈值 ===
                if neighbor_pop > 0 and my_suit > SUIT_THRESHOLD:
                    if gradient < 0:
                        # 邻居适宜度低于我，邻居种群向我扩散
                        rate = base_rate * (1.0 - gradient * 0.5)
                        inflow += neighbor_pop * rate * 0.25
                    elif gradient < 0.3:
                        # 我适宜度稍低但仍可接受，少量流入
                        rate = base_rate * 0.3
                        inflow += neighbor_pop * rate * 0.25
        
        # 限制最大流出（不能超过当前种群的40%）
        if current > 0:
            outflow = ti.min(outflow, current * 0.4)
        else:
            outflow = 0.0
        
        new_pop[s, i, j] = current - outflow + inflow


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
    
    Args:
        pop: 种群张量 (S, H, W)
        env: 环境张量 (C, H, W) - [temp, humidity, altitude, resource, land, sea, coast]
        species_prefs: 物种偏好 (S, 7)
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
    
    for s, i, j in ti.ndrange(S, H, W):
        if pop[s, i, j] <= 0:
            result[s, i, j] = 0.0
            continue
        
        # === 1. 温度死亡率 ===
        temp_channel = 1 if C_env > 1 else 0
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
        humidity = env[1, i, j] if C_env > 2 else env[0, i, j] * 0.5
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
            prey_scarcity_mortality = (1.0 - prey_density_norm) * 0.2
        
        # === 6. 外部压力死亡率 ===
        external_pressure = 0.0
        for c in range(C_pressure):
            external_pressure += pressure_overlay[c, i, j]
        external_mortality = ti.min(0.5, external_pressure * 0.1)
        
        # === 综合死亡率 ===
        total_mortality = (
            temp_mortality * temp_weight +
            humidity_mortality * 0.1 +
            competition_mortality * competition_weight +
            resource_mortality * resource_weight +
            prey_scarcity_mortality +
            external_mortality +
            base_mortality
        )
        
        # 时代缩放：早期时代死亡率略低
        if era_scaling > 1.5:
            scale_factor = ti.max(0.7, 1.0 / ti.pow(era_scaling, 0.2))
            total_mortality *= scale_factor
        
        result[s, i, j] = ti.max(0.01, ti.min(0.95, total_mortality))


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
        kernel_execute_migration(pop, migration_scores, result_3d, migration_rates, 0.1)
        kernel_multifactor_mortality(
            pop, env, prefs, params, trophic, pressure, result_3d,
            0.05, 0.3, 0.2, 0.15, 1.0, 1.0
        )
        
        # 同步 Taichi 运行时
        ti.sync()
        
        logger.info("[Taichi] 所有内核预编译完成")
        
    except Exception as e:
        logger.warning(f"[Taichi] 内核预编译失败（将在首次使用时编译）: {e}")


# 在模块加载时预编译
_precompile_all_kernels()


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
    """GPU并行计算最终适应度"""
    for i in range(n):
        # 营养级分数
        trophic_score = ti.max(0.2, 1.2 - trophic[i] * 0.25)
        
        # 加权综合
        fit = (
            pop_amp[i] * 0.40 +
            survival_amp[i] * 0.30 +
            repro_amp[i] * 0.20 +
            trophic_score * 0.10
        )
        
        # 年龄惩罚
        if age[i] > 20:
            fit *= 0.90
        elif age[i] > 10:
            fit *= 0.95
        
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


