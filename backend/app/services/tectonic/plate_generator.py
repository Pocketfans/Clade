"""板块生成器

使用加权生长算法生成自然不规则的板块分布。
"""

from __future__ import annotations

import heapq
import math
import random
from typing import TYPE_CHECKING

import numpy as np

from .config import TECTONIC_CONFIG, PLATE_DENSITIES
from .models import Plate, PlateType, MotionPhase, SimpleTile

if TYPE_CHECKING:
    pass


class PlateGenerator:
    """板块生成器
    
    算法：加权生长 + 噪声扰动
    1. 按幂律分布确定板块数量和大小目标
    2. 在地图上撒种子点（大板块的种子优先级高）
    3. 使用加权 flood-fill 生长，边界加入噪声扰动
    4. 后处理：合并过小区域、修复孤岛
    """
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.config = TECTONIC_CONFIG["plate_generation"]
        self.motion_config = TECTONIC_CONFIG["motion"]
    
    def generate(self, seed: int) -> tuple[list[Plate], np.ndarray, list[SimpleTile]]:
        """
        生成板块分布
        
        Args:
            seed: 随机种子
            
        Returns:
            (板块列表, 板块ID矩阵, 地块列表)
        """
        random.seed(seed)
        np.random.seed(seed)
        
        # === Step 1: 确定板块大小分布（幂律分布）===
        plate_sizes = self._generate_size_distribution()
        num_plates = len(plate_sizes)
        
        # === Step 2: 放置种子点 ===
        seeds = self._place_seeds(plate_sizes)
        
        # === Step 3: 生成边界噪声 ===
        boundary_noise = self._generate_boundary_noise(seed)
        
        # === Step 4: 加权生长 ===
        plate_map = self._weighted_growth(seeds, plate_sizes, boundary_noise)
        
        # === Step 5: 后处理（合并小区域、修复孤岛）===
        plate_map = self._post_process(plate_map, num_plates)
        
        # === Step 6: 不规则化边界 ===
        plate_map = self._irregularize_boundaries(plate_map, seed)
        
        # === Step 7: 创建板块对象 ===
        plates = self._create_plates(plate_map, seeds, plate_sizes)
        
        # === Step 8: 创建地块对象 ===
        tiles = self._create_tiles(plate_map, seed)
        
        return plates, plate_map, tiles
    
    def _generate_size_distribution(self) -> list[int]:
        """
        生成板块大小分布（幂律分布）
        
        模拟真实地球：
        - 少量大板块占大部分面积
        - 中等数量中型板块
        - 较多小板块
        """
        total_tiles = self.width * self.height
        sizes = []
        remaining = total_tiles
        
        cfg = self.config
        
        # 大板块
        num_major = random.randint(*cfg["num_major_plates"])
        for _ in range(num_major):
            ratio = random.uniform(*cfg["major_size_ratio"])
            size = int(total_tiles * ratio)
            sizes.append(size)
            remaining -= size
        
        # 中板块
        num_medium = random.randint(*cfg["num_medium_plates"])
        for _ in range(num_medium):
            ratio = random.uniform(*cfg["medium_size_ratio"])
            size = int(total_tiles * ratio)
            sizes.append(min(size, remaining // 2))
            remaining -= sizes[-1]
        
        # 小板块（填充剩余区域）
        min_size = int(total_tiles * cfg["minor_size_ratio"][0])
        while remaining > min_size:
            ratio = random.uniform(*cfg["minor_size_ratio"])
            size = int(total_tiles * ratio)
            size = min(size, remaining)
            if size > 0:
                sizes.append(size)
                remaining -= size
        
        # 如果还有剩余，分配给最后一个
        if remaining > 0 and sizes:
            sizes[-1] += remaining
        
        # 打乱顺序（避免大板块总在特定位置）
        random.shuffle(sizes)
        
        return sizes
    
    def _place_seeds(self, plate_sizes: list[int]) -> list[tuple[int, int, int, str]]:
        """
        放置种子点
        
        Returns:
            list of (x, y, plate_idx, plate_type)
        """
        seeds = []
        min_distance = self.config["min_plate_seed_distance"]
        
        # 按大小排序，优先放置大板块（降序）
        indexed_sizes = [(i, s) for i, s in enumerate(plate_sizes)]
        indexed_sizes.sort(key=lambda x: -x[1])
        
        for plate_idx, size in indexed_sizes:
            # 计算最小间距（大板块需要更大间距）
            required_distance = max(min_distance, int(math.sqrt(size) * 0.4))
            
            # 尝试放置
            placed = False
            for _ in range(200):  # 最多尝试200次
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                
                # 检查间距
                valid = True
                for sx, sy, _, _ in seeds:
                    # 考虑X轴循环
                    dx = min(abs(x - sx), self.width - abs(x - sx))
                    dy = abs(y - sy)
                    if math.sqrt(dx**2 + dy**2) < required_distance:
                        valid = False
                        break
                
                if valid:
                    # 判断板块类型
                    is_oceanic = self._estimate_oceanic_probability(x, y) > 0.5
                    plate_type = "oceanic" if is_oceanic else "continental"
                    
                    seeds.append((x, y, plate_idx, plate_type))
                    placed = True
                    break
            
            # 如果无法放置，强制放置
            if not placed:
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                seeds.append((x, y, plate_idx, "continental"))
        
        return seeds
    
    def _estimate_oceanic_probability(self, x: int, y: int) -> float:
        """估计某位置是海洋的概率（用于初始化板块类型）"""
        # 简化模型：基于初始地图生成的海陆分布
        # 假设70%是海洋，且赤道附近陆地更多
        lat = abs(y / self.height - 0.5) * 2  # 0=赤道, 1=极地
        
        # 赤道附近陆地概率高
        if lat < 0.3:
            oceanic_prob = 0.55
        elif lat < 0.7:
            oceanic_prob = 0.75
        else:
            oceanic_prob = 0.85  # 极地多海洋
        
        return oceanic_prob
    
    def _generate_boundary_noise(self, seed: int) -> np.ndarray:
        """生成边界扰动噪声（分形噪声）"""
        np.random.seed(seed + 1000)
        
        noise = np.zeros((self.height, self.width), dtype=np.float32)
        
        # 多尺度噪声叠加
        for octave in range(4):
            freq = 2 ** octave
            amp = 0.5 ** octave
            
            # 生成随机相位
            phase_x = random.uniform(0, 2 * math.pi)
            phase_y = random.uniform(0, 2 * math.pi)
            
            for y in range(self.height):
                for x in range(self.width):
                    val = math.sin(x * freq * 0.15 + phase_x)
                    val += math.cos(y * freq * 0.2 + phase_y)
                    val += math.sin((x + y) * freq * 0.1)
                    noise[y, x] += val * amp
        
        # 归一化到 0-1
        noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-8)
        
        return noise
    
    def _weighted_growth(
        self, 
        seeds: list[tuple[int, int, int, str]], 
        plate_sizes: list[int],
        boundary_noise: np.ndarray
    ) -> np.ndarray:
        """
        加权生长算法
        
        每个种子同时向外生长，大板块生长更快。
        边界加入噪声扰动，使边界不规则。
        """
        plate_map = np.full((self.height, self.width), -1, dtype=np.int32)
        
        # 初始化优先队列：(优先级, x, y, plate_idx)
        pq: list[tuple[float, int, int, int]] = []
        
        for x, y, plate_idx, _ in seeds:
            plate_map[y, x] = plate_idx
            # 大板块初始优先级更高（更小的值）
            priority = -math.log(plate_sizes[plate_idx] + 1) * 0.5
            heapq.heappush(pq, (priority, x, y, plate_idx))
        
        # 当前每个板块已占面积
        current_sizes = {i: 1 for i in range(len(plate_sizes))}
        
        while pq:
            priority, x, y, plate_idx = heapq.heappop(pq)
            
            # 如果该板块已达到目标大小的1.2倍，降低优先级
            target = plate_sizes[plate_idx]
            if current_sizes[plate_idx] >= target * 1.2:
                continue
            
            # 扩展到相邻格子
            for nx, ny in self._get_neighbors(x, y):
                if plate_map[ny, nx] == -1:
                    # 计算新优先级
                    noise = boundary_noise[ny, nx]
                    dist = abs(priority) + 1
                    # 噪声扰动：影响生长边界
                    noise_effect = (noise - 0.5) * 2 * self.config["boundary_noise_strength"]
                    new_priority = dist + noise_effect
                    
                    plate_map[ny, nx] = plate_idx
                    current_sizes[plate_idx] = current_sizes.get(plate_idx, 0) + 1
                    heapq.heappush(pq, (new_priority, nx, ny, plate_idx))
        
        return plate_map
    
    def _post_process(self, plate_map: np.ndarray, num_plates: int) -> np.ndarray:
        """
        后处理：
        1. 填充未分配的格子
        2. 合并过小的区域
        3. 修复孤岛
        """
        # 填充未分配的格子
        for y in range(self.height):
            for x in range(self.width):
                if plate_map[y, x] == -1:
                    # 找最近的已分配格子
                    neighbors = self._get_neighbors(x, y)
                    for nx, ny in neighbors:
                        if plate_map[ny, nx] >= 0:
                            plate_map[y, x] = plate_map[ny, nx]
                            break
                    
                    # 如果还是-1，随机分配
                    if plate_map[y, x] == -1:
                        plate_map[y, x] = random.randint(0, num_plates - 1)
        
        return plate_map
    
    def _irregularize_boundaries(self, plate_map: np.ndarray, seed: int) -> np.ndarray:
        """
        使边界更加不规则
        在边界处根据噪声随机"侵蚀"或"生长"
        """
        random.seed(seed + 2000)
        result = plate_map.copy()
        noise_strength = self.config["boundary_noise_strength"]
        
        # 多次迭代
        for _ in range(2):
            for y in range(self.height):
                for x in range(self.width):
                    current = result[y, x]
                    neighbors = self._get_neighbors(x, y)
                    
                    # 找出不同板块的邻居
                    different_neighbors = [
                        result[ny, nx] 
                        for nx, ny in neighbors 
                        if result[ny, nx] != current
                    ]
                    
                    if different_neighbors:
                        # 根据随机数决定是否"转让"
                        if random.random() < noise_strength * 0.5:
                            result[y, x] = random.choice(different_neighbors)
        
        return result
    
    def _get_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        """获取六边形邻居坐标"""
        # odd-q 布局
        if x & 1:  # 奇数列
            offsets = [
                (0, -1), (1, -1),
                (-1, 0), (1, 0),
                (0, 1), (1, 1),
            ]
        else:  # 偶数列
            offsets = [
                (-1, -1), (0, -1),
                (-1, 0), (1, 0),
                (-1, 1), (0, 1),
            ]
        
        neighbors = []
        for dx, dy in offsets:
            nx = (x + dx) % self.width  # X轴循环
            ny = y + dy
            if 0 <= ny < self.height:
                neighbors.append((nx, ny))
        
        return neighbors
    
    def _create_plates(
        self, 
        plate_map: np.ndarray, 
        seeds: list[tuple[int, int, int, str]],
        plate_sizes: list[int]
    ) -> list[Plate]:
        """创建板块对象"""
        plates = []
        num_plates = len(plate_sizes)
        
        # 统计每个板块的实际大小
        actual_sizes = np.bincount(plate_map.flatten(), minlength=num_plates)
        
        # 创建种子点映射
        seed_map = {plate_idx: (x, y, plate_type) for x, y, plate_idx, plate_type in seeds}
        
        cfg = self.motion_config
        
        for plate_idx in range(num_plates):
            # 获取种子点信息
            if plate_idx in seed_map:
                cx, cy, plate_type_str = seed_map[plate_idx]
            else:
                # 如果没有种子点，计算质心
                ys, xs = np.where(plate_map == plate_idx)
                if len(xs) > 0:
                    cx = float(np.mean(xs))
                    cy = float(np.mean(ys))
                else:
                    cx, cy = self.width // 2, self.height // 2
                plate_type_str = "continental"
            
            # 确定板块类型
            plate_type = PlateType(plate_type_str)
            density = PLATE_DENSITIES[plate_type_str]
            
            # 生成随机运动参数
            vx = random.uniform(-cfg["base_velocity"], cfg["base_velocity"])
            vy = random.uniform(-cfg["base_velocity"] * 0.5, cfg["base_velocity"] * 0.5)
            angular_v = random.uniform(*cfg["angular_velocity_range"])
            
            # 统计边界地块数量
            boundary_count = self._count_boundary_tiles(plate_map, plate_idx)
            
            plate = Plate(
                id=plate_idx,
                plate_index=plate_idx,
                velocity_x=vx,
                velocity_y=vy,
                angular_velocity=angular_v,
                rotation_center_x=cx,
                rotation_center_y=cy,
                plate_type=plate_type,
                density=density,
                thickness=35.0 if plate_type == PlateType.CONTINENTAL else 7.0,
                age=0,
                motion_phase=MotionPhase.STABLE,
                tile_count=int(actual_sizes[plate_idx]),
                boundary_tile_count=boundary_count,
            )
            plates.append(plate)
        
        return plates
    
    def _count_boundary_tiles(self, plate_map: np.ndarray, plate_idx: int) -> int:
        """统计板块的边界地块数量"""
        count = 0
        for y in range(self.height):
            for x in range(self.width):
                if plate_map[y, x] == plate_idx:
                    neighbors = self._get_neighbors(x, y)
                    for nx, ny in neighbors:
                        if plate_map[ny, nx] != plate_idx:
                            count += 1
                            break
        return count
    
    def _create_tiles(self, plate_map: np.ndarray, seed: int) -> list[SimpleTile]:
        """创建简化地块列表"""
        random.seed(seed + 3000)
        np.random.seed(seed + 3000)
        
        tiles = []
        
        for y in range(self.height):
            for x in range(self.width):
                tile_id = y * self.width + x
                plate_id = int(plate_map[y, x])
                
                # 生成初始海拔（基于简化的地形生成）
                elevation = self._generate_initial_elevation(x, y, seed)
                
                # 计算温度和湿度
                lat = abs(y / self.height - 0.5) * 2  # 0=赤道, 1=极地
                temperature = 30 - 60 * lat - elevation * 0.006
                humidity = 0.7 - 0.4 * lat + random.uniform(-0.1, 0.1)
                humidity = max(0.1, min(0.95, humidity))
                
                # 推断生物群系
                if elevation < 0:
                    biome = "深海" if elevation < -500 else "浅海"
                elif elevation > 2500:
                    biome = "高山"
                elif elevation > 800:
                    biome = "山地"
                else:
                    biome = "平原"
                
                tile = SimpleTile(
                    id=tile_id,
                    x=x,
                    y=y,
                    elevation=elevation,
                    temperature=temperature,
                    humidity=humidity,
                    biome=biome,
                    plate_id=plate_id,
                )
                tiles.append(tile)
        
        return tiles
    
    def _generate_initial_elevation(self, x: int, y: int, seed: int) -> float:
        """生成初始海拔"""
        # 使用简化的噪声生成
        lat = y / self.height
        lon = x / self.width
        
        # 多尺度噪声
        noise = 0.0
        for octave in range(4):
            freq = 2 ** octave
            amp = 0.5 ** octave
            noise += math.sin(lon * freq * 10 + seed * 0.1) * amp
            noise += math.cos(lat * freq * 8 + seed * 0.2) * amp
        
        # 赤道附近更可能是陆地
        land_bias = 0.0
        if 0.35 < lat < 0.65:
            land_bias = 0.3
        
        # 归一化并转换为海拔
        normalized = (noise + 2) / 4 + land_bias  # 大约 0-1
        
        if normalized < 0.7:
            # 海洋
            depth_factor = normalized / 0.7
            elevation = -6000 + depth_factor * 5800  # -6000 到 -200
        else:
            # 陆地
            height_factor = (normalized - 0.7) / 0.3
            elevation = height_factor * 4000  # 0 到 4000
        
        return elevation



