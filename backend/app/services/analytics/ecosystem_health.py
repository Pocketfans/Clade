"""生态系统健康指标服务

计算各种生态系统健康指标，用于前端仪表盘展示和游戏分析。
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Sequence

from ...models.species import Species

logger = logging.getLogger(__name__)


@dataclass
class TrophicDistribution:
    """营养级分布"""
    level: float
    species_count: int
    total_population: int
    total_biomass: float
    percentage: float  # 物种数占比


@dataclass
class ExtinctionRisk:
    """灭绝风险评估"""
    lineage_code: str
    common_name: str
    risk_level: str  # "critical", "endangered", "vulnerable", "safe"
    risk_score: float  # 0-1
    reasons: list[str]


@dataclass
class EcosystemHealthReport:
    """生态系统健康报告"""
    # 多样性指标
    shannon_index: float  # Shannon-Wiener多样性指数 (0-5+)
    simpson_index: float  # Simpson多样性指数 (0-1)
    species_richness: int  # 物种丰富度（存活物种数）
    evenness: float  # 均匀度 (0-1)
    
    # 营养级结构
    trophic_distribution: list[TrophicDistribution]
    trophic_balance_score: float  # 营养级平衡分数 (0-1)
    
    # 灭绝风险
    extinction_risks: list[ExtinctionRisk]
    critical_count: int
    endangered_count: int
    
    # 共生网络
    symbiotic_connections: int  # 共生关系数量
    network_connectivity: float  # 网络连通性 (0-1)
    
    # 整体健康评分
    overall_health_score: float  # 0-100
    health_grade: str  # A/B/C/D/F
    health_summary: str  # 健康状况总结


class EcosystemHealthService:
    """生态系统健康分析服务"""
    
    def __init__(self):
        self.min_viable_population = 100  # 最小可存活种群
        self.critical_threshold = 0.8  # 高风险阈值
        self.endangered_threshold = 0.5  # 濒危阈值
        self.vulnerable_threshold = 0.3  # 易危阈值
    
    def analyze(self, species_list: Sequence[Species], extinct_codes: set[str] = None) -> EcosystemHealthReport:
        """分析生态系统健康状况
        
        Args:
            species_list: 所有存活物种列表
            extinct_codes: 已灭绝物种代码集合（用于依赖关系分析）
        """
        if extinct_codes is None:
            extinct_codes = set()
        
        alive_species = [sp for sp in species_list if sp.status == "alive"]
        
        if not alive_species:
            return self._empty_report()
        
        # 计算各项指标
        shannon, simpson, evenness = self._calculate_diversity_indices(alive_species)
        trophic_dist = self._calculate_trophic_distribution(alive_species)
        trophic_balance = self._calculate_trophic_balance(trophic_dist)
        extinction_risks = self._assess_extinction_risks(alive_species, extinct_codes)
        symbiotic_stats = self._analyze_symbiotic_network(alive_species)
        
        # 统计风险等级
        critical_count = sum(1 for r in extinction_risks if r.risk_level == "critical")
        endangered_count = sum(1 for r in extinction_risks if r.risk_level == "endangered")
        
        # 计算整体健康分数
        overall_score = self._calculate_overall_health(
            shannon, simpson, evenness, trophic_balance,
            len(alive_species), critical_count, endangered_count,
            symbiotic_stats["connectivity"]
        )
        
        health_grade = self._score_to_grade(overall_score)
        health_summary = self._generate_health_summary(
            overall_score, len(alive_species), critical_count, endangered_count, trophic_balance
        )
        
        return EcosystemHealthReport(
            shannon_index=shannon,
            simpson_index=simpson,
            species_richness=len(alive_species),
            evenness=evenness,
            trophic_distribution=trophic_dist,
            trophic_balance_score=trophic_balance,
            extinction_risks=extinction_risks,
            critical_count=critical_count,
            endangered_count=endangered_count,
            symbiotic_connections=symbiotic_stats["connections"],
            network_connectivity=symbiotic_stats["connectivity"],
            overall_health_score=overall_score,
            health_grade=health_grade,
            health_summary=health_summary,
        )
    
    def _calculate_diversity_indices(self, species_list: list[Species]) -> tuple[float, float, float]:
        """计算多样性指数
        
        Returns:
            (Shannon指数, Simpson指数, 均匀度)
        """
        if not species_list:
            return 0.0, 0.0, 0.0
        
        # 获取种群数量
        populations = []
        for sp in species_list:
            pop = int(sp.morphology_stats.get("population", 0) or 0)
            if pop > 0:
                populations.append(pop)
        
        if not populations:
            return 0.0, 0.0, 0.0
        
        total_pop = sum(populations)
        n_species = len(populations)
        
        # 计算各物种比例
        proportions = [p / total_pop for p in populations]
        
        # Shannon-Wiener指数: H' = -Σ(pi * ln(pi))
        shannon = 0.0
        for p in proportions:
            if p > 0:
                shannon -= p * math.log(p)
        
        # Simpson指数: D = 1 - Σ(pi^2)
        simpson = 1.0 - sum(p ** 2 for p in proportions)
        
        # 均匀度: E = H' / ln(S)
        max_diversity = math.log(n_species) if n_species > 1 else 1.0
        evenness = shannon / max_diversity if max_diversity > 0 else 0.0
        
        return round(shannon, 3), round(simpson, 3), round(evenness, 3)
    
    def _calculate_trophic_distribution(self, species_list: list[Species]) -> list[TrophicDistribution]:
        """计算营养级分布"""
        trophic_groups: dict[float, list[Species]] = {}
        
        for sp in species_list:
            level = round(sp.trophic_level)  # 取整为营养级
            if level not in trophic_groups:
                trophic_groups[level] = []
            trophic_groups[level].append(sp)
        
        total_species = len(species_list)
        distributions = []
        
        for level in sorted(trophic_groups.keys()):
            group = trophic_groups[level]
            total_pop = sum(int(sp.morphology_stats.get("population", 0) or 0) for sp in group)
            total_biomass = sum(
                int(sp.morphology_stats.get("population", 0) or 0) * 
                float(sp.morphology_stats.get("body_weight_g", 1.0) or 1.0)
                for sp in group
            )
            
            distributions.append(TrophicDistribution(
                level=level,
                species_count=len(group),
                total_population=total_pop,
                total_biomass=total_biomass,
                percentage=round(len(group) / total_species * 100, 1) if total_species > 0 else 0
            ))
        
        return distributions
    
    def _calculate_trophic_balance(self, trophic_dist: list[TrophicDistribution]) -> float:
        """计算营养级平衡分数
        
        理想情况：
        - T1 (生产者) 应该占主导
        - T2 (初级消费者) 应该是T1的10-30%
        - T3+ (高级消费者) 应该逐级递减
        """
        if not trophic_dist:
            return 0.0
        
        # 找到各营养级
        t1_biomass = 0.0
        t2_biomass = 0.0
        t3plus_biomass = 0.0
        
        for td in trophic_dist:
            if td.level < 2:
                t1_biomass += td.total_biomass
            elif td.level < 3:
                t2_biomass += td.total_biomass
            else:
                t3plus_biomass += td.total_biomass
        
        # 计算比例
        total_biomass = t1_biomass + t2_biomass + t3plus_biomass
        if total_biomass == 0:
            return 0.0
        
        # 理想比例：T1:T2:T3+ ≈ 80:15:5
        ideal_t1_ratio = 0.80
        ideal_t2_ratio = 0.15
        ideal_t3_ratio = 0.05
        
        actual_t1_ratio = t1_biomass / total_biomass
        actual_t2_ratio = t2_biomass / total_biomass
        actual_t3_ratio = t3plus_biomass / total_biomass
        
        # 计算与理想比例的偏差
        deviation = (
            abs(actual_t1_ratio - ideal_t1_ratio) +
            abs(actual_t2_ratio - ideal_t2_ratio) +
            abs(actual_t3_ratio - ideal_t3_ratio)
        ) / 2  # 最大偏差为2
        
        balance_score = max(0.0, 1.0 - deviation)
        return round(balance_score, 3)
    
    def _assess_extinction_risks(
        self, species_list: list[Species], extinct_codes: set[str]
    ) -> list[ExtinctionRisk]:
        """评估各物种的灭绝风险"""
        risks = []
        
        for sp in species_list:
            risk_score = 0.0
            reasons = []
            
            population = int(sp.morphology_stats.get("population", 0) or 0)
            
            # 1. 种群规模风险
            if population < self.min_viable_population:
                risk_score += 0.4
                reasons.append(f"种群极小({population})")
            elif population < self.min_viable_population * 10:
                risk_score += 0.2
                reasons.append(f"种群较小({population})")
            
            # 2. 依赖物种灭绝风险
            dependencies = getattr(sp, 'symbiotic_dependencies', []) or []
            dep_strength = getattr(sp, 'dependency_strength', 0.0) or 0.0
            
            if dependencies:
                extinct_deps = [d for d in dependencies if d in extinct_codes]
                if extinct_deps:
                    risk_score += dep_strength * 0.5
                    reasons.append(f"依赖物种已灭绝({len(extinct_deps)}种)")
            
            # 3. 基因多样性风险
            gene_diversity = sp.hidden_traits.get("gene_diversity", 0.5)
            if gene_diversity < 0.3:
                risk_score += 0.2
                reasons.append("基因多样性低")
            
            # 4. 环境敏感性风险
            env_sens = sp.hidden_traits.get("environment_sensitivity", 0.5)
            if env_sens > 0.7:
                risk_score += 0.15
                reasons.append("环境敏感度高")
            
            # 5. 是否被压制
            is_suppressed = getattr(sp, 'is_suppressed', False) or False
            if is_suppressed:
                risk_score += 0.1
                reasons.append("正在被压制")
            
            # 6. 是否受保护（降低风险）
            is_protected = getattr(sp, 'is_protected', False) or False
            if is_protected:
                risk_score = max(0.0, risk_score - 0.2)
                reasons.append("受保护物种")
            
            # 确定风险等级
            risk_score = min(1.0, risk_score)
            if risk_score >= self.critical_threshold:
                risk_level = "critical"
            elif risk_score >= self.endangered_threshold:
                risk_level = "endangered"
            elif risk_score >= self.vulnerable_threshold:
                risk_level = "vulnerable"
            else:
                risk_level = "safe"
            
            # 只返回有风险的物种
            if risk_level != "safe":
                risks.append(ExtinctionRisk(
                    lineage_code=sp.lineage_code,
                    common_name=sp.common_name,
                    risk_level=risk_level,
                    risk_score=round(risk_score, 2),
                    reasons=reasons if reasons else ["综合风险评估"]
                ))
        
        # 按风险分数排序
        risks.sort(key=lambda r: r.risk_score, reverse=True)
        return risks
    
    def _analyze_symbiotic_network(self, species_list: list[Species]) -> dict:
        """分析共生网络"""
        connections = 0
        total_possible = len(species_list) * (len(species_list) - 1) / 2 if len(species_list) > 1 else 1
        
        species_codes = {sp.lineage_code for sp in species_list}
        
        for sp in species_list:
            dependencies = getattr(sp, 'symbiotic_dependencies', []) or []
            # 只计算与当前存活物种的连接
            valid_deps = [d for d in dependencies if d in species_codes]
            connections += len(valid_deps)
        
        # 每个连接被计算了一次（单向），连通性 = 实际连接 / 可能连接
        connectivity = connections / total_possible if total_possible > 0 else 0.0
        
        return {
            "connections": connections,
            "connectivity": round(min(1.0, connectivity), 3)
        }
    
    def _calculate_overall_health(
        self, shannon: float, simpson: float, evenness: float,
        trophic_balance: float, species_count: int,
        critical_count: int, endangered_count: int,
        network_connectivity: float
    ) -> float:
        """计算整体生态系统健康分数 (0-100)"""
        score = 0.0
        
        # 1. 多样性贡献 (30分)
        # Shannon指数通常在1-4之间，超过3算非常好
        diversity_score = min(30, shannon * 10)
        score += diversity_score
        
        # 2. 均匀度贡献 (15分)
        score += evenness * 15
        
        # 3. 营养级平衡贡献 (20分)
        score += trophic_balance * 20
        
        # 4. 物种丰富度贡献 (15分)
        # 假设100种为满分
        richness_score = min(15, species_count / 100 * 15)
        score += richness_score
        
        # 5. 濒危物种扣分 (-20分)
        extinction_penalty = critical_count * 5 + endangered_count * 2
        score -= min(20, extinction_penalty)
        
        # 6. 网络连通性贡献 (10分)
        score += network_connectivity * 10
        
        # 7. Simpson多样性加分 (10分)
        score += simpson * 10
        
        return round(max(0, min(100, score)), 1)
    
    def _score_to_grade(self, score: float) -> str:
        """分数转等级"""
        if score >= 80:
            return "A"
        elif score >= 60:
            return "B"
        elif score >= 40:
            return "C"
        elif score >= 20:
            return "D"
        else:
            return "F"
    
    def _generate_health_summary(
        self, score: float, species_count: int,
        critical_count: int, endangered_count: int,
        trophic_balance: float
    ) -> str:
        """生成健康状况总结"""
        parts = []
        
        # 整体评价
        if score >= 80:
            parts.append(f"生态系统健康状况优秀({score:.0f}分)")
        elif score >= 60:
            parts.append(f"生态系统健康状况良好({score:.0f}分)")
        elif score >= 40:
            parts.append(f"生态系统健康状况一般({score:.0f}分)")
        else:
            parts.append(f"生态系统健康状况堪忧({score:.0f}分)")
        
        # 物种数量
        parts.append(f"共{species_count}个存活物种")
        
        # 濒危情况
        if critical_count > 0:
            parts.append(f"⚠️ {critical_count}种极危物种")
        if endangered_count > 0:
            parts.append(f"⚠️ {endangered_count}种濒危物种")
        
        # 营养级平衡
        if trophic_balance < 0.3:
            parts.append("营养级结构严重失衡")
        elif trophic_balance < 0.6:
            parts.append("营养级结构略有失衡")
        
        return "；".join(parts) + "。"
    
    def _empty_report(self) -> EcosystemHealthReport:
        """返回空报告"""
        return EcosystemHealthReport(
            shannon_index=0.0,
            simpson_index=0.0,
            species_richness=0,
            evenness=0.0,
            trophic_distribution=[],
            trophic_balance_score=0.0,
            extinction_risks=[],
            critical_count=0,
            endangered_count=0,
            symbiotic_connections=0,
            network_connectivity=0.0,
            overall_health_score=0.0,
            health_grade="F",
            health_summary="生态系统中没有存活物种。",
        )

