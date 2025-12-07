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








