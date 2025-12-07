"""
Taichi 内核定义模块

此模块在导入时初始化 Taichi 并定义所有内核。
如果 Taichi 不可用，则此模块的导入会失败。
"""

import taichi as ti

# 初始化 Taichi（在模块级别）
# 使用 offline_cache 加速后续运行
ti.init(arch=ti.gpu, default_fp=ti.f32, offline_cache=True)


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
            
            # 转换为权重 (近=1, 远=0)
            result[s, i, j] = ti.max(0.0, 1.0 - dist / max_distance)
        else:
            result[s, i, j] = 1.0


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
    """批量计算所有物种的迁徙决策分数 - Taichi 并行
    
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
        # 当前地块已有种群，不需要迁入
        if pop[s, i, j] > 0:
            migration_scores[s, i, j] = 0.0
            continue
        
        death_rate = death_rates[s]
        base_score = suitability[s, i, j] * 0.5 + distance_weights[s, i, j] * 0.5
        
        # 压力驱动迁徙 - 死亡率高时更愿意迁移
        if death_rate > pressure_threshold:
            # 高压力模式：适宜度权重更高，愿意走得更远
            pressure_boost = ti.min(0.5, (death_rate - pressure_threshold) * 2.0)
            base_score = suitability[s, i, j] * (0.6 + pressure_boost * 0.2) + distance_weights[s, i, j] * (0.4 - pressure_boost * 0.2)
        
        # 添加随机扰动（用格子坐标模拟）
        noise = 0.85 + 0.3 * ti.sin(ti.cast(i * 17 + j * 31 + s * 7, ti.f32))
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
    
    Args:
        pop: 当前种群张量 (S, H, W)
        migration_scores: 迁徙分数张量 (S, H, W)
        new_pop: 迁徙后的种群张量 (S, H, W)
        migration_rates: 每个物种的迁徙比例 (S,)
        score_threshold: 分数阈值，低于此值不迁徙
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    for s in range(S):
        # 计算该物种的总种群和总迁徙分数
        total_pop = 0.0
        total_score = 0.0
        
        for i, j in ti.ndrange(H, W):
            total_pop += pop[s, i, j]
            if migration_scores[s, i, j] > score_threshold:
                total_score += migration_scores[s, i, j]
        
        # 迁徙量
        migrate_amount = total_pop * migration_rates[s]
        
        # 按分数比例分配迁徙种群
        for i, j in ti.ndrange(H, W):
            if pop[s, i, j] > 0:
                # 原有种群保留部分
                new_pop[s, i, j] = pop[s, i, j] * (1.0 - migration_rates[s])
            else:
                new_pop[s, i, j] = 0.0
            
            # 分配迁入种群
            if total_score > 0 and migration_scores[s, i, j] > score_threshold:
                score_ratio = migration_scores[s, i, j] / total_score
                new_pop[s, i, j] += migrate_amount * score_ratio


@ti.kernel
def kernel_advanced_diffusion(
    pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    suitability: ti.types.ndarray(dtype=ti.f32, ndim=3),
    new_pop: ti.types.ndarray(dtype=ti.f32, ndim=3),
    base_rate: ti.f32,
):
    """带适宜度引导的高级扩散 - Taichi 并行
    
    种群会优先向适宜度更高的地块扩散。
    
    Args:
        pop: 种群张量 (S, H, W)
        suitability: 适宜度张量 (S, H, W)
        new_pop: 扩散后的种群张量 (S, H, W)
        base_rate: 基础扩散率
    """
    S, H, W = pop.shape[0], pop.shape[1], pop.shape[2]
    
    for s, i, j in ti.ndrange(S, H, W):
        current = pop[s, i, j]
        if current <= 0:
            new_pop[s, i, j] = 0.0
            continue
        
        # 计算到邻居的扩散
        outflow = 0.0
        inflow = 0.0
        
        # 四个邻居方向
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        for di, dj in ti.static(neighbors):
            ni = i + di
            nj = j + dj
            
            if 0 <= ni < H and 0 <= nj < W:
                my_suit = suitability[s, i, j]
                neighbor_suit = suitability[s, ni, nj]
                
                # 适宜度梯度决定扩散方向和强度
                # 如果邻居适宜度更高，更多种群流向邻居
                gradient = neighbor_suit - my_suit
                
                if gradient > 0:
                    # 向高适宜度流出
                    rate = base_rate * (1.0 + gradient)
                    outflow += current * rate * 0.25
                elif gradient < 0:
                    # 从低适宜度流入
                    rate = base_rate * (1.0 - gradient)
                    inflow += pop[s, ni, nj] * rate * 0.25
        
        # 限制最大流出
        outflow = ti.min(outflow, current * 0.5)
        
        new_pop[s, i, j] = current - outflow + inflow









