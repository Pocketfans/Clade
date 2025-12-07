"""
生态位和杂交张量计算模块测试

测试内容：
1. NicheTensorCompute - 地块重叠、谱系bonus、栖息地bonus
2. HybridizationTensorCompute - 同域矩阵、遗传距离、杂交候选筛选
3. 性能基准测试
"""

import pytest
import numpy as np
from dataclasses import dataclass
from typing import Any

# 模拟 Species 对象
@dataclass
class MockSpecies:
    """模拟物种对象"""
    id: int
    lineage_code: str
    trophic_level: float
    habitat_type: str
    morphology_stats: dict
    abstract_traits: dict = None
    status: str = "alive"
    created_turn: int = 0
    
    def __post_init__(self):
        if self.abstract_traits is None:
            self.abstract_traits = {}


@dataclass
class MockHabitatPopulation:
    """模拟栖息地种群对象"""
    species_id: int
    tile_id: int
    population: int = 1000


class TestNicheTensorCompute:
    """测试生态位张量计算"""
    
    def test_compute_tile_overlap_matrix_basic(self):
        """测试基本的地块重叠矩阵计算"""
        from ..niche_tensor import NicheTensorCompute
        
        compute = NicheTensorCompute()
        
        # 创建测试数据
        species_ids = [1, 2, 3]
        habitat_cache = {
            1: {0, 1, 2},      # 物种1在地块0,1,2
            2: {1, 2, 3},      # 物种2在地块1,2,3
            3: {10, 11, 12},   # 物种3在地块10,11,12（无重叠）
        }
        
        overlap_matrix, metrics = compute.compute_tile_overlap_matrix(
            species_ids, habitat_cache
        )
        
        # 验证形状
        assert overlap_matrix.shape == (3, 3)
        
        # 验证对角线为1
        np.testing.assert_array_almost_equal(
            np.diag(overlap_matrix), [1, 1, 1]
        )
        
        # 物种1和2有重叠（地块1,2）
        assert overlap_matrix[0, 1] > 0.1
        assert overlap_matrix[0, 1] == overlap_matrix[1, 0]  # 对称
        
        # 物种3和其他物种无重叠
        assert overlap_matrix[0, 2] == 0.1  # 最小重叠因子
        assert overlap_matrix[1, 2] == 0.1
        
        # 验证指标
        assert metrics.species_count == 3
        assert metrics.tile_count > 0
    
    def test_compute_tile_overlap_empty_habitat(self):
        """测试空栖息地缓存"""
        from ..niche_tensor import NicheTensorCompute
        
        compute = NicheTensorCompute()
        
        species_ids = [1, 2]
        habitat_cache = {}
        
        overlap_matrix, metrics = compute.compute_tile_overlap_matrix(
            species_ids, habitat_cache
        )
        
        # 无栖息地数据时返回默认中等重叠
        assert overlap_matrix.shape == (2, 2)
        np.testing.assert_array_almost_equal(
            overlap_matrix, [[0.5, 0.5], [0.5, 0.5]]
        )
    
    def test_compute_lineage_bonus_matrix(self):
        """测试谱系前缀bonus矩阵"""
        from ..niche_tensor import NicheTensorCompute
        
        compute = NicheTensorCompute()
        
        lineage_codes = ["A1a", "A1b", "A2a", "B1a"]
        
        bonus_matrix, time_ms = compute.compute_lineage_bonus_matrix(lineage_codes)
        
        # 验证形状
        assert bonus_matrix.shape == (4, 4)
        
        # 对角线为0
        np.testing.assert_array_almost_equal(np.diag(bonus_matrix), [0, 0, 0, 0])
        
        # A1a 和 A1b 共享前缀 "A1"，应有bonus
        assert bonus_matrix[0, 1] == 0.15
        
        # A1a 和 A2a 共享前缀 "A"，但长度<2，无bonus
        assert bonus_matrix[0, 2] == 0.0
        
        # A1a 和 B1a 无共同前缀
        assert bonus_matrix[0, 3] == 0.0
        
        # 对称性
        assert bonus_matrix[0, 1] == bonus_matrix[1, 0]
    
    def test_compute_habitat_bonus_matrix(self):
        """测试栖息地类型bonus矩阵"""
        from ..niche_tensor import NicheTensorCompute
        
        compute = NicheTensorCompute()
        
        habitat_types = ["marine", "marine", "terrestrial", "coastal"]
        
        bonus_matrix, time_ms = compute.compute_habitat_bonus_matrix(habitat_types)
        
        # 验证形状
        assert bonus_matrix.shape == (4, 4)
        
        # 对角线为0
        np.testing.assert_array_almost_equal(np.diag(bonus_matrix), [0, 0, 0, 0])
        
        # 相同栖息地类型
        assert bonus_matrix[0, 1] == 0.10  # marine-marine
        
        # 兼容栖息地类型
        assert bonus_matrix[0, 3] == 0.05  # marine-coastal
        
        # 不兼容栖息地
        assert bonus_matrix[0, 2] == 0.0   # marine-terrestrial


class TestHybridizationTensorCompute:
    """测试杂交张量计算"""
    
    def create_mock_species(self, n: int) -> list[MockSpecies]:
        """创建模拟物种列表"""
        species_list = []
        for i in range(n):
            sp = MockSpecies(
                id=i + 1,
                lineage_code=f"A{i // 3}{chr(97 + i % 3)}",  # A0a, A0b, A0c, A1a, ...
                trophic_level=2.0 + (i % 3) * 0.5,
                habitat_type="terrestrial",
                morphology_stats={
                    "body_length_cm": 10 + i * 5,
                    "body_weight_g": 100 + i * 50,
                    "population": 1000 + i * 100,
                },
                created_turn=i,
            )
            species_list.append(sp)
        return species_list
    
    def create_mock_habitats(
        self, species_list: list[MockSpecies], shared_ratio: float = 0.5
    ) -> list[MockHabitatPopulation]:
        """创建模拟栖息地数据"""
        habitats = []
        n = len(species_list)
        
        for i, sp in enumerate(species_list):
            # 每个物种占据3个地块
            base_tile = i * 2
            tiles = [base_tile, base_tile + 1, base_tile + 2]
            
            # 相邻物种共享一些地块
            if i > 0 and np.random.random() < shared_ratio:
                tiles.append(base_tile - 1)  # 与前一个物种共享
            
            for tile_id in tiles:
                habitats.append(MockHabitatPopulation(
                    species_id=sp.id,
                    tile_id=tile_id,
                    population=sp.morphology_stats.get("population", 1000),
                ))
        
        return habitats
    
    def test_build_sympatry_matrix_basic(self):
        """测试同域矩阵构建"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        species_list = self.create_mock_species(5)
        habitats = self.create_mock_habitats(species_list, shared_ratio=1.0)
        
        shared, total, ratio = compute.build_sympatry_matrix(species_list, habitats)
        
        # 验证形状
        assert shared.shape == (5, 5)
        assert total.shape == (5, 5)
        assert ratio.shape == (5, 5)
        
        # 对角线
        for i in range(5):
            assert shared[i, i] >= 3  # 每个物种至少3个地块
        
        # 同域比例在 [0, 1] 范围内
        assert np.all(ratio >= 0)
        assert np.all(ratio <= 1)
    
    def test_build_genetic_distance_matrix(self):
        """测试遗传距离矩阵构建"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        species_list = self.create_mock_species(5)
        
        distance = compute.build_genetic_distance_matrix(species_list)
        
        # 验证形状
        assert distance.shape == (5, 5)
        
        # 对角线为0
        np.testing.assert_array_almost_equal(np.diag(distance), [0, 0, 0, 0, 0])
        
        # 对称性
        np.testing.assert_array_almost_equal(distance, distance.T)
        
        # 距离在 [0, 1] 范围内
        assert np.all(distance >= 0)
        assert np.all(distance <= 1)
    
    def test_compute_fertility(self):
        """测试可育性计算"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        # 构建测试距离矩阵
        distance = np.array([
            [0.0, 0.10, 0.30, 0.60, 0.80],
            [0.10, 0.0, 0.20, 0.50, 0.90],
            [0.30, 0.20, 0.0, 0.40, 0.75],
            [0.60, 0.50, 0.40, 0.0, 0.65],
            [0.80, 0.90, 0.75, 0.65, 0.0],
        ])
        
        fertility = compute.compute_fertility(distance)
        
        # 验证形状
        assert fertility.shape == (5, 5)
        
        # 对角线为0
        np.testing.assert_array_almost_equal(np.diag(fertility), [0, 0, 0, 0, 0])
        
        # 低距离 -> 高可育性
        assert fertility[0, 1] > 0.9  # 距离0.10
        
        # 高距离 -> 低/无可育性
        assert fertility[0, 4] == 0.0  # 距离0.80 > 0.70
        
        # 可育性在 [0, 1] 范围内
        assert np.all(fertility >= 0)
        assert np.all(fertility <= 1)
    
    def test_find_hybrid_candidates_basic(self):
        """测试杂交候选查找"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        species_list = self.create_mock_species(10)
        habitats = self.create_mock_habitats(species_list, shared_ratio=0.8)
        
        candidates, metrics = compute.find_hybrid_candidates(
            species_list=species_list,
            habitat_data=habitats,
            min_population=500,
            max_genetic_distance=0.70,
            min_shared_tiles=1,
            max_candidates=20,
        )
        
        # 验证指标
        assert metrics.species_count == 10
        assert metrics.total_time_ms > 0
        
        # 验证候选
        for cand in candidates:
            # 索引有效
            assert 0 <= cand.species1_idx < 10
            assert 0 <= cand.species2_idx < 10
            assert cand.species1_idx < cand.species2_idx  # 上三角
            
            # 代码非空
            assert cand.species1_code
            assert cand.species2_code
            
            # 数值范围
            assert cand.shared_tiles >= 1
            assert 0 <= cand.sympatry_ratio <= 1
            assert 0 <= cand.genetic_distance <= 0.70
            assert 0 <= cand.fertility <= 1
            assert cand.hybrid_score >= 0
    
    def test_find_hybrid_candidates_no_candidates(self):
        """测试无候选情况"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        # 只有一个物种
        species_list = self.create_mock_species(1)
        habitats = self.create_mock_habitats(species_list)
        
        candidates, metrics = compute.find_hybrid_candidates(
            species_list=species_list,
            habitat_data=habitats,
        )
        
        assert len(candidates) == 0
        assert metrics.species_count == 1


class TestPerformanceScaling:
    """性能扩展测试"""
    
    def create_large_dataset(self, n_species: int, n_tiles_per_species: int = 5):
        """创建大规模测试数据集"""
        species_list = []
        habitats = []
        
        for i in range(n_species):
            sp = MockSpecies(
                id=i + 1,
                lineage_code=f"A{i // 10}{chr(97 + i % 10)}",
                trophic_level=1.5 + (i % 5) * 0.5,
                habitat_type=["marine", "terrestrial", "freshwater"][i % 3],
                morphology_stats={
                    "body_length_cm": 10 + i,
                    "body_weight_g": 100 + i * 10,
                    "population": 1000 + i * 100,
                },
                created_turn=i // 5,
            )
            species_list.append(sp)
            
            # 创建栖息地数据
            base_tile = i * 3
            for j in range(n_tiles_per_species):
                habitats.append(MockHabitatPopulation(
                    species_id=sp.id,
                    tile_id=base_tile + j,
                ))
                # 与相邻物种共享一些地块
                if i > 0 and j == 0:
                    habitats.append(MockHabitatPopulation(
                        species_id=sp.id,
                        tile_id=base_tile - 1,
                    ))
        
        return species_list, habitats
    
    @pytest.mark.parametrize("n_species", [10, 30, 50])
    def test_niche_tensor_scaling(self, n_species: int):
        """测试生态位张量计算的扩展性"""
        from ..niche_tensor import NicheTensorCompute
        
        compute = NicheTensorCompute()
        
        species_list, habitats = self.create_large_dataset(n_species)
        
        # 构建 habitat_cache
        habitat_cache = {}
        for hab in habitats:
            if hab.species_id not in habitat_cache:
                habitat_cache[hab.species_id] = set()
            habitat_cache[hab.species_id].add(hab.tile_id)
        
        species_ids = [sp.id for sp in species_list]
        
        # 测试地块重叠计算
        overlap_matrix, metrics = compute.compute_tile_overlap_matrix(
            species_ids, habitat_cache
        )
        
        assert overlap_matrix.shape == (n_species, n_species)
        
        # 性能要求：50物种应在 100ms 内完成
        if n_species <= 50:
            assert metrics.total_time_ms < 100, \
                f"地块重叠计算太慢: {metrics.total_time_ms:.1f}ms for {n_species} species"
        
        print(f"\n[NicheTensor] {n_species} 物种: {metrics.total_time_ms:.2f}ms")
    
    @pytest.mark.parametrize("n_species", [10, 30, 50])
    def test_hybridization_tensor_scaling(self, n_species: int):
        """测试杂交张量计算的扩展性"""
        from ..hybridization_tensor import HybridizationTensorCompute
        
        compute = HybridizationTensorCompute()
        
        species_list, habitats = self.create_large_dataset(n_species)
        
        candidates, metrics = compute.find_hybrid_candidates(
            species_list=species_list,
            habitat_data=habitats,
            min_population=500,
            max_candidates=50,
        )
        
        assert metrics.species_count == n_species
        
        # 性能要求：50物种应在 200ms 内完成
        if n_species <= 50:
            assert metrics.total_time_ms < 200, \
                f"杂交候选筛选太慢: {metrics.total_time_ms:.1f}ms for {n_species} species"
        
        print(
            f"\n[HybridTensor] {n_species} 物种: "
            f"{metrics.total_time_ms:.2f}ms, "
            f"候选={metrics.candidate_pairs}, "
            f"筛选={metrics.filtered_pairs}"
        )


class TestIntegration:
    """集成测试"""
    
    def test_niche_and_hybridization_consistency(self):
        """测试生态位和杂交模块的一致性"""
        from ..niche_tensor import NicheTensorCompute
        from ..hybridization_tensor import HybridizationTensorCompute
        
        niche_compute = NicheTensorCompute()
        hybrid_compute = HybridizationTensorCompute()
        
        # 创建测试数据
        species_list = []
        for i in range(5):
            sp = MockSpecies(
                id=i + 1,
                lineage_code=f"A{i}a",
                trophic_level=2.0,
                habitat_type="terrestrial",
                morphology_stats={
                    "body_length_cm": 10,
                    "body_weight_g": 100,
                    "population": 1000,
                },
            )
            species_list.append(sp)
        
        habitats = [
            MockHabitatPopulation(species_id=1, tile_id=0),
            MockHabitatPopulation(species_id=1, tile_id=1),
            MockHabitatPopulation(species_id=2, tile_id=1),
            MockHabitatPopulation(species_id=2, tile_id=2),
            MockHabitatPopulation(species_id=3, tile_id=10),
        ]
        
        # 测试两个模块的地块重叠计算
        # NicheTensorCompute
        habitat_cache = {}
        for hab in habitats:
            if hab.species_id not in habitat_cache:
                habitat_cache[hab.species_id] = set()
            habitat_cache[hab.species_id].add(hab.tile_id)
        
        species_ids = [sp.id for sp in species_list]
        niche_overlap, _ = niche_compute.compute_tile_overlap_matrix(
            species_ids[:3], habitat_cache
        )
        
        # HybridizationTensorCompute
        shared, _, sympatry = hybrid_compute.build_sympatry_matrix(
            species_list[:3], habitats
        )
        
        # 物种1和2有共享地块1
        assert niche_overlap[0, 1] > 0.1  # Jaccard > 最小值
        assert shared[0, 1] >= 1  # 至少1个共享地块
        
        # 物种3与1,2无共享
        assert niche_overlap[0, 2] == 0.1  # 最小重叠因子
        assert shared[0, 2] == 0

