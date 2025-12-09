"""张量化竞争计算模块 - Taichi GPU 加速版

将亲缘竞争计算完全张量化，使用Taichi GPU内核，消除Python循环。

核心优化：
1. 适应度计算：Taichi GPU并行
2. 竞争矩阵：Taichi GPU并行，O(S²) 全并行
3. 亲缘矩阵：预处理后GPU并行计算

内核定义在 taichi_hybrid_kernels.py 中（需要在Taichi初始化后定义）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

# 导入Taichi内核（GPU-only 模式）
import taichi as ti
from . import taichi_hybrid_kernels as _kernels
TAICHI_AVAILABLE = True  # GPU-only: 如果导入失败会直接抛出错误

if TYPE_CHECKING:
    from ..models.species import Species
    from ..models.config import EcologyBalanceConfig

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class TensorCompetitionResult:
    """张量化竞争计算结果"""
    mortality_modifiers: np.ndarray  # (S,) 死亡率修正
    reproduction_modifiers: np.ndarray  # (S,) 繁殖率修正
    fitness_scores: np.ndarray  # (S,) 适应度分数
    species_codes: list[str]  # 物种代码列表
    competition_matrix: np.ndarray | None = None


# ============================================================================
# 计算器类
# ============================================================================

class TensorCompetitionCalculator:
    """Taichi GPU 加速的竞争计算器"""
    
    def __init__(self, config: EcologyBalanceConfig | None = None):
        self._config = config
        self._lineage_pattern = re.compile(r'^(.+?)([A-Z]\d+)$')
        self._taichi_initialized = False
    
    def reload_config(self, config: EcologyBalanceConfig) -> None:
        self._config = config
    
    def calculate_all(
        self,
        species_list: Sequence[Species],
        niche_overlaps: dict[str, float] | None = None,
    ) -> TensorCompetitionResult:
        """一次性计算所有物种的竞争结果（Taichi GPU加速）"""
        n = len(species_list)
        codes = [sp.lineage_code for sp in species_list]
        
        if n == 0:
            return TensorCompetitionResult(
                mortality_modifiers=np.array([], dtype=np.float32),
                reproduction_modifiers=np.array([], dtype=np.float32),
                fitness_scores=np.array([], dtype=np.float32),
                species_codes=[],
            )
        
        cfg = self._config
        if cfg is None or not cfg.enable_kin_competition:
            return TensorCompetitionResult(
                mortality_modifiers=np.zeros(n, dtype=np.float32),
                reproduction_modifiers=np.zeros(n, dtype=np.float32),
                fitness_scores=np.full(n, 0.5, dtype=np.float32),
                species_codes=codes,
            )
        
        # GPU-only 模式：Taichi 始终可用
        if not TAICHI_AVAILABLE:
            raise RuntimeError("[GPU-only] Taichi GPU 不可用，请检查 GPU 驱动")
        
        # ========== 1. 提取物种数据 ==========
        data = self._extract_species_data(species_list)
        
        # ========== 2. 计算适应度（GPU）==========
        fitness = self._compute_fitness_gpu(data, n)
        
        # ========== 3. 构建亲缘矩阵（CPU预处理）==========
        kinship = self._build_kinship_matrix(codes)
        
        # ========== 4. 构建重叠矩阵（GPU）==========
        overlap = self._build_overlap_matrix_gpu(codes, niche_overlaps, n)
        
        # ========== 5. 构建营养级掩码（GPU）==========
        trophic_mask = self._build_trophic_mask_gpu(data['trophic'], n)
        
        # ========== 6. 计算竞争修正（GPU）==========
        mortality_mods, repro_mods = self._compute_competition_gpu(
            fitness, kinship, overlap, trophic_mask, data['repro'], cfg, n
        )
        
        # 同步GPU
        ti.sync()
        
        logger.info(
            f"[张量竞争-GPU] n={n}, fitness: [{fitness.min():.2f}, {fitness.max():.2f}], "
            f"std={fitness.std():.3f}, mort_mod: [{mortality_mods.min():.3f}, {mortality_mods.max():.3f}]"
        )
        
        return TensorCompetitionResult(
            mortality_modifiers=mortality_mods,
            reproduction_modifiers=repro_mods,
            fitness_scores=fitness,
            species_codes=codes,
        )
    
    def _extract_species_data(self, species_list: Sequence[Species]) -> dict[str, np.ndarray]:
        """提取物种数据为NumPy数组"""
        n = len(species_list)
        
        pop = np.zeros(n, dtype=np.float32)
        death_rate = np.zeros(n, dtype=np.float32)
        repro = np.zeros(n, dtype=np.float32)
        body_size = np.zeros(n, dtype=np.float32)
        trophic = np.zeros(n, dtype=np.float32)
        age = np.zeros(n, dtype=np.float32)
        
        for i, sp in enumerate(species_list):
            pop[i] = float(sp.morphology_stats.get("population", 0) or 0)
            death_rate[i] = float(sp.morphology_stats.get("death_rate", 0.5) or 0.5)
            repro[i] = sp.abstract_traits.get("繁殖速度", 5)
            body_size[i] = sp.abstract_traits.get("体型", 5)
            trophic[i] = sp.trophic_level
            age[i] = sp.morphology_stats.get("age_turns", 0) or 0
        
        return {
            'pop': pop, 'death_rate': death_rate, 'repro': repro,
            'body_size': body_size, 'trophic': trophic, 'age': age,
        }
    
    def _compute_fitness_gpu(self, data: dict[str, np.ndarray], n: int) -> np.ndarray:
        """GPU计算适应度"""
        if n <= 1:
            return np.full(n, 0.5, dtype=np.float32)
        
        # 1. 种群排名（对数化）
        log_pop = np.log1p(data['pop']).astype(np.float32)
        pop_ranks = self._rank_normalize_gpu(log_pop, higher_is_better=True)
        
        # 2. 生存排名
        survival_ranks = self._rank_normalize_gpu(data['death_rate'], higher_is_better=False)
        
        # 3. 繁殖效率排名
        repro_eff = (data['repro'] / np.maximum(data['body_size'], 1.0)).astype(np.float32)
        repro_ranks = self._rank_normalize_gpu(repro_eff, higher_is_better=True)
        
        # 4. 放大差距（GPU）
        pop_amp = np.zeros(n, dtype=np.float32)
        survival_amp = np.zeros(n, dtype=np.float32)
        repro_amp = np.zeros(n, dtype=np.float32)
        
        _kernels.kernel_amplify_difference(pop_ranks, pop_amp, 1.5, n)
        _kernels.kernel_amplify_difference(survival_ranks, survival_amp, 2.0, n)
        _kernels.kernel_amplify_difference(repro_ranks, repro_amp, 1.5, n)
        
        # 5. 计算最终适应度（GPU）
        fitness = np.zeros(n, dtype=np.float32)
        _kernels.kernel_compute_fitness_1d(
            pop_amp, survival_amp, repro_amp,
            data['trophic'], data['age'], fitness, n
        )
        
        return fitness
    
    def _rank_normalize_gpu(self, values: np.ndarray, higher_is_better: bool = True) -> np.ndarray:
        """排名归一化（NumPy实现，小数组CPU更快）"""
        n = len(values)
        if n <= 1:
            return np.full(n, 0.5, dtype=np.float32)
        
        sorted_indices = np.argsort(values)
        if higher_is_better:
            sorted_indices = sorted_indices[::-1]
        
        ranks = np.zeros(n, dtype=np.float32)
        ranks[sorted_indices] = np.arange(n, dtype=np.float32)
        ranks = 1.0 - ranks / (n - 1)
        
        return ranks
    
    def _build_kinship_matrix(self, codes: list[str]) -> np.ndarray:
        """构建亲缘矩阵（CPU预处理，因为需要字符串操作）"""
        n = len(codes)
        kinship = np.full((n, n), 999, dtype=np.int32)
        np.fill_diagonal(kinship, 0)
        
        # 预计算祖先链
        ancestors_list = [self._parse_ancestors(code) for code in codes]
        
        for i in range(n):
            anc_i = ancestors_list[i]
            set_i = set(anc_i)
            for j in range(i + 1, n):
                anc_j = ancestors_list[j]
                common = set_i & set(anc_j)
                if common:
                    for gen, anc in enumerate(anc_i):
                        if anc in common:
                            gen_j = anc_j.index(anc) if anc in anc_j else 999
                            kinship[i, j] = max(gen, gen_j)
                            kinship[j, i] = kinship[i, j]
                            break
        
        return kinship
    
    def _parse_ancestors(self, code: str) -> list[str]:
        """解析lineage_code得到祖先链"""
        chain = [code]
        current = code
        
        while True:
            match = self._lineage_pattern.match(current)
            if match and match.group(1):
                current = match.group(1)
                chain.append(current)
            else:
                break
        
        return chain
    
    def _build_overlap_matrix_gpu(
        self, codes: list[str], niche_overlaps: dict[str, float] | None, n: int
    ) -> np.ndarray:
        """GPU构建重叠矩阵"""
        if niche_overlaps is None:
            return np.full((n, n), 0.5, dtype=np.float32)
        
        overlaps = np.array([niche_overlaps.get(c, 0.5) for c in codes], dtype=np.float32)
        overlap_matrix = np.zeros((n, n), dtype=np.float32)
        
        _kernels.kernel_build_overlap_matrix_2d(overlaps, overlap_matrix, n)
        
        return overlap_matrix
    
    def _build_trophic_mask_gpu(self, trophic: np.ndarray, n: int) -> np.ndarray:
        """GPU构建营养级掩码"""
        mask = np.zeros((n, n), dtype=np.float32)
        _kernels.kernel_build_trophic_mask_2d(trophic, mask, n)
        return mask
    
    def _compute_competition_gpu(
        self,
        fitness: np.ndarray,
        kinship: np.ndarray,
        overlap: np.ndarray,
        trophic_mask: np.ndarray,
        repro: np.ndarray,
        cfg: EcologyBalanceConfig,
        n: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """GPU计算竞争修正"""
        mortality_mods = np.zeros(n, dtype=np.float32)
        repro_mods = np.zeros(n, dtype=np.float32)
        
        contested_coef = getattr(cfg, 'kin_contested_penalty_coefficient', 0.12)
        
        _kernels.kernel_compute_competition_mods(
            fitness, kinship, overlap, trophic_mask, repro,
            mortality_mods, repro_mods, n,
            cfg.kin_generation_threshold,
            float(cfg.kin_competition_multiplier),
            float(cfg.non_kin_competition_multiplier),
            float(cfg.kin_disadvantage_threshold),
            float(cfg.kin_winner_mortality_reduction),
            float(cfg.kin_loser_mortality_penalty),
            float(contested_coef),
        )
        
        return mortality_mods, repro_mods
    


# ============================================================================
# 全局单例和便捷函数
# ============================================================================

_tensor_competition_calculator: TensorCompetitionCalculator | None = None


def get_tensor_competition_calculator() -> TensorCompetitionCalculator:
    """获取张量竞争计算器单例"""
    global _tensor_competition_calculator
    if _tensor_competition_calculator is None:
        _tensor_competition_calculator = TensorCompetitionCalculator()
    return _tensor_competition_calculator


def calculate_competition_tensor(
    species_list: Sequence[Species],
    config: EcologyBalanceConfig,
    niche_overlaps: dict[str, float] | None = None,
) -> TensorCompetitionResult:
    """便捷函数：一次性计算所有物种的竞争结果（Taichi GPU加速）"""
    calc = get_tensor_competition_calculator()
    calc.reload_config(config)
    return calc.calculate_all(species_list, niche_overlaps)
