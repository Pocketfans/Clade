"""
神性系统路由 - 能量、成就、提示

此模块负责：
- 能量系统管理
- 成就系统
- 游戏提示
- 杂交控制
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from .dependencies import get_container, get_session, get_species_repository, require_not_running

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["divine"])


# ========== 能量系统 ==========

@router.get("/energy", tags=["energy"])
def get_energy_status() -> dict:
    """获取能量状态"""
    from ..services.system.divine_energy import energy_service
    return energy_service.get_status()


@router.get("/energy/costs", tags=["energy"])
def get_energy_costs() -> dict:
    """获取所有操作的能量消耗定义"""
    from ..services.system.divine_energy import energy_service
    return {"costs": energy_service.get_all_costs()}


@router.get("/energy/history", tags=["energy"])
def get_energy_history(limit: int = 20) -> dict:
    """获取能量交易历史"""
    from ..services.system.divine_energy import energy_service
    return {"history": energy_service.get_history(limit)}


@router.post("/energy/calculate", tags=["energy"])
def calculate_energy_cost(request: dict) -> dict:
    """计算操作的能量消耗"""
    from ..services.system.divine_energy import energy_service
    
    action = request.get("action", "")
    
    if action == "pressure" and "pressures" in request:
        cost = energy_service.get_pressure_cost(request["pressures"])
    else:
        cost = energy_service.get_cost(action, **request)
    
    can_afford, _ = energy_service.can_afford(action, **request)
    
    return {
        "action": action,
        "cost": cost,
        "can_afford": can_afford,
        "current_energy": energy_service.get_state().current,
    }


@router.post("/energy/toggle", tags=["energy"])
def toggle_energy_system(request: dict) -> dict:
    """启用/禁用能量系统"""
    from ..services.system.divine_energy import energy_service
    
    energy_service.enabled = request.get("enabled", True)
    return {
        "success": True,
        "enabled": energy_service.enabled,
    }


@router.post("/energy/set", tags=["energy"])
def set_energy(request: dict) -> dict:
    """设置能量参数（GM模式）"""
    from ..services.system.divine_energy import energy_service
    
    energy_service.set_energy(
        current=request.get("current"),
        maximum=request.get("maximum"),
        regen=request.get("regen"),
    )
    return energy_service.get_status()


# ========== 成就系统 ==========

@router.get("/achievements", tags=["achievements"])
def get_achievements() -> dict:
    """获取所有成就及其解锁状态"""
    from ..services.analytics.achievements import achievement_service
    return {
        "achievements": achievement_service.get_all_achievements(),
        "stats": achievement_service.get_stats(),
    }


@router.get("/achievements/unlocked", tags=["achievements"])
def get_unlocked_achievements() -> dict:
    """获取已解锁的成就"""
    from ..services.analytics.achievements import achievement_service
    return {"unlocked": achievement_service.get_unlocked()}


@router.get("/achievements/pending", tags=["achievements"])
def get_pending_achievement_unlocks() -> dict:
    """获取待通知的成就解锁事件（获取后清空）"""
    from ..services.analytics.achievements import achievement_service
    
    pending = achievement_service.get_pending_unlocks()
    achievements = []
    for ach_id in pending:
        ach = achievement_service.get_achievement(ach_id)
        if ach:
            achievements.append({
                "id": ach_id,
                "name": ach.get("name", ""),
                "description": ach.get("description", ""),
                "icon": ach.get("icon", "🏆"),
            })
    
    return {"pending": achievements}


@router.post("/achievements/exploration/{feature}", tags=["achievements"])
def record_exploration(feature: str) -> dict:
    """记录玩家探索功能（用于解锁探索者成就）"""
    from ..services.analytics.achievements import achievement_service
    
    # 有效的功能列表
    valid_features = {
        "lineage_tree", "food_web", "species_detail",
        "pressure_config", "save_load", "achievements",
        "ecosystem_health", "migration", "hybridization",
    }
    
    if feature not in valid_features:
        return {"success": False, "error": "Invalid feature"}
    
    achievement_service.record_exploration(feature)
    return {"success": True, "feature": feature}


@router.post("/achievements/reset", tags=["achievements"])
def reset_achievements() -> dict:
    """重置所有成就进度（新存档时调用）"""
    from ..services.analytics.achievements import achievement_service
    
    achievement_service.reset()
    return {"success": True}


# ========== 提示系统 ==========

@router.get("/hints", tags=["hints"])
def get_game_hints(
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取当前游戏状态的智能提示"""
    from ..services.analytics.game_hints import game_hints_service
    
    species_repo = container.species_repository
    all_species = species_repo.list_species()
    
    # 收集游戏状态
    context = {
        "turn": container.simulation_engine.turn_counter,
        "alive_species": sum(1 for sp in all_species if sp.status == "alive"),
        "extinct_species": sum(1 for sp in all_species if sp.status == "extinct"),
        "total_population": sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in all_species if sp.status == "alive"
        ),
    }
    
    hints = game_hints_service.get_hints(context)
    return {"hints": hints}


@router.post("/hints/clear", tags=["hints"])
def clear_hints_cooldown() -> dict:
    """清除提示冷却（新存档时调用）"""
    from ..services.analytics.game_hints import game_hints_service
    
    game_hints_service.clear_cooldown()
    return {"success": True}


# ========== 杂交控制 ==========

@router.get("/hybridization/candidates", tags=["hybridization"])
def get_hybridization_candidates(
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取可杂交的物种对"""
    species_repo = container.species_repository
    hybridization_service = container.hybridization_service
    
    all_species = species_repo.list_species()
    alive_species = [sp for sp in all_species if sp.status == "alive"]
    
    candidates = []
    checked_pairs = set()
    
    for sp1 in alive_species:
        for sp2 in alive_species:
            if sp1.lineage_code >= sp2.lineage_code:
                continue
            
            pair_key = f"{sp1.lineage_code}-{sp2.lineage_code}"
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            
            can_hybrid, fertility = hybridization_service.can_hybridize(sp1, sp2)
            if can_hybrid:
                candidates.append({
                    "species_a": {
                        "lineage_code": sp1.lineage_code,
                        "common_name": sp1.common_name,
                        "latin_name": sp1.latin_name,
                        "genus_code": sp1.genus_code,
                    },
                    "species_b": {
                        "lineage_code": sp2.lineage_code,
                        "common_name": sp2.common_name,
                        "latin_name": sp2.latin_name,
                        "genus_code": sp2.genus_code,
                    },
                    "fertility": round(fertility, 3),
                    "genus": sp1.genus_code,
                })
    
    return {
        "candidates": candidates,
        "total": len(candidates),
    }


@router.post("/hybridization/execute", tags=["hybridization"])
async def execute_hybridization(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """执行杂交（使用AI生成杂交物种）（模拟运行时禁止）"""
    from ..services.system.divine_energy import energy_service
    from ..services.analytics.achievements import achievement_service
    
    code_a = request.get("species_a", "")
    code_b = request.get("species_b", "")
    
    if not code_a or not code_b:
        raise HTTPException(status_code=400, detail="请提供两个物种代码")
    
    species_repo = container.species_repository
    hybridization_service = container.hybridization_service
    engine = container.simulation_engine
    
    species_a = species_repo.get_by_lineage(code_a)
    species_b = species_repo.get_by_lineage(code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {code_b} 不存在")
    
    if species_a.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {code_a} 已灭绝")
    if species_b.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {code_b} 已灭绝")
    
    can_hybrid, fertility = hybridization_service.can_hybridize(species_a, species_b)
    if not can_hybrid:
        raise HTTPException(status_code=400, detail="这两个物种无法杂交")
    
    current_turn = engine.turn_counter
    can_afford, cost = energy_service.can_afford("hybridize")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！杂交需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    success, msg = energy_service.spend(
        "hybridize",
        current_turn,
        details=f"杂交 {species_a.common_name} × {species_b.common_name}"
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    all_species = species_repo.list_species()
    existing_codes = {sp.lineage_code for sp in all_species}
    
    hybrid = await hybridization_service.create_hybrid_async(
        species_a, species_b, current_turn,
        existing_codes=existing_codes
    )
    if not hybrid:
        energy_service.add_energy(cost, "杂交失败退还")
        raise HTTPException(status_code=500, detail="杂交失败")
    
    species_repo.upsert(hybrid)
    achievement_service._unlock("hybrid_creator", current_turn)
    
    return {
        "success": True,
        "hybrid": {
            "lineage_code": hybrid.lineage_code,
            "latin_name": hybrid.latin_name,
            "common_name": hybrid.common_name,
            "description": hybrid.description,
            "fertility": hybrid.hybrid_fertility,
            "parent_codes": hybrid.hybrid_parent_codes,
        },
        "energy_spent": cost,
        "energy_remaining": energy_service.get_state().current,
    }


@router.get("/hybridization/preview", tags=["hybridization"])
def preview_hybridization(
    species_a: str,
    species_b: str,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """预览杂交结果"""
    from ..services.system.divine_energy import energy_service
    
    species_repo = container.species_repository
    hybridization_service = container.hybridization_service
    genetic_calculator = container.genetic_distance_calculator
    
    sp_a = species_repo.get_by_lineage(species_a)
    sp_b = species_repo.get_by_lineage(species_b)
    
    if not sp_a:
        raise HTTPException(status_code=404, detail=f"物种 {species_a} 不存在")
    if not sp_b:
        raise HTTPException(status_code=404, detail=f"物种 {species_b} 不存在")
    
    can_hybrid, fertility = hybridization_service.can_hybridize(sp_a, sp_b)
    
    if not can_hybrid:
        if sp_a.genus_code != sp_b.genus_code:
            reason = "不同属的物种无法杂交"
        elif sp_a.lineage_code == sp_b.lineage_code:
            reason = "同一物种无法杂交"
        else:
            distance = genetic_calculator.calculate_distance(sp_a, sp_b)
            reason = f"遗传距离过大 ({distance:.2f} >= 0.5)"
        
        return {
            "can_hybridize": False,
            "reason": reason,
            "fertility": 0,
            "energy_cost": energy_service.get_cost("hybridize"),
        }
    
    hybrid_code = f"{sp_a.lineage_code}×{sp_b.lineage_code}"
    hybrid_name = f"{sp_a.common_name}×{sp_b.common_name}杂交种"
    
    predicted_trophic = max(sp_a.trophic_level, sp_b.trophic_level)
    combined_capabilities = list(set(sp_a.capabilities + sp_b.capabilities))
    
    return {
        "can_hybridize": True,
        "fertility": round(fertility, 3),
        "energy_cost": energy_service.get_cost("hybridize"),
        "can_afford": energy_service.can_afford("hybridize")[0],
        "preview": {
            "lineage_code": hybrid_code,
            "common_name": hybrid_name,
            "predicted_trophic_level": predicted_trophic,
            "combined_capabilities": combined_capabilities,
            "parent_traits_merged": True,
        },
    }


# ========== 强行杂交 ==========

FORCED_HYBRIDIZATION_COST = 50


@router.get("/hybridization/force/preview", tags=["hybridization"])
def preview_forced_hybridization(
    species_a: str,
    species_b: str,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """预览强行杂交结果"""
    from ..services.system.divine_energy import energy_service
    
    species_repo = container.species_repository
    genetic_calculator = container.genetic_distance_calculator
    
    sp_a = species_repo.get_by_lineage(species_a)
    sp_b = species_repo.get_by_lineage(species_b)
    
    if not sp_a:
        raise HTTPException(status_code=404, detail=f"物种 {species_a} 不存在")
    if not sp_b:
        raise HTTPException(status_code=404, detail=f"物种 {species_b} 不存在")
    
    if sp_a.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {species_a} 已灭绝")
    if sp_b.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {species_b} 已灭绝")
    
    distance = genetic_calculator.calculate_distance(sp_a, sp_b)
    estimated_fertility = max(0.0, 0.3 - distance * 0.5)
    stability = max(0.1, 1.0 - distance)
    
    return {
        "can_force": True,
        "energy_cost": FORCED_HYBRIDIZATION_COST,
        "can_afford": energy_service.get_state().current >= FORCED_HYBRIDIZATION_COST,
        "genetic_distance": round(distance, 3),
        "estimated_fertility": round(estimated_fertility, 3),
        "genetic_stability": round(stability, 3),
        "warnings": [
            "强行杂交产物可能不育或基因不稳定",
            "能量消耗是普通杂交的5倍",
        ],
        "preview": {
            "chimera_name": f"{sp_a.common_name}×{sp_b.common_name}嵌合体",
            "is_chimera": True,
        },
    }


@router.post("/hybridization/force/execute", tags=["hybridization"])
async def execute_forced_hybridization(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """执行强行杂交（模拟运行时禁止）"""
    from ..services.system.divine_energy import energy_service
    from ..services.analytics.achievements import achievement_service
    
    code_a = request.get("species_a", "")
    code_b = request.get("species_b", "")
    
    if not code_a or not code_b:
        raise HTTPException(status_code=400, detail="请提供两个物种代码")
    
    species_repo = container.species_repository
    hybridization_service = container.hybridization_service
    engine = container.simulation_engine
    
    species_a = species_repo.get_by_lineage(code_a)
    species_b = species_repo.get_by_lineage(code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {code_b} 不存在")
    
    current_turn = engine.turn_counter
    current_energy = energy_service.get_state().current
    
    if current_energy < FORCED_HYBRIDIZATION_COST:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！强行杂交需要 {FORCED_HYBRIDIZATION_COST} 能量"
        )
    
    success, msg = energy_service.spend(
        "forced_hybridize",
        current_turn,
        details=f"强行杂交 {species_a.common_name} × {species_b.common_name}",
        cost_override=FORCED_HYBRIDIZATION_COST,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    all_species = species_repo.list_species()
    existing_codes = {sp.lineage_code for sp in all_species}
    
    chimera = await hybridization_service.create_forced_hybrid_async(
        species_a, species_b, current_turn,
        existing_codes=existing_codes
    )
    if not chimera:
        energy_service.add_energy(FORCED_HYBRIDIZATION_COST, "强行杂交失败退还")
        raise HTTPException(status_code=500, detail="强行杂交失败")
    
    species_repo.upsert(chimera)
    achievement_service._unlock("chimera_creator", current_turn)
    
    return {
        "success": True,
        "chimera": {
            "lineage_code": chimera.lineage_code,
            "latin_name": chimera.latin_name,
            "common_name": chimera.common_name,
            "description": chimera.description,
            "fertility": chimera.hybrid_fertility,
            "parent_codes": chimera.hybrid_parent_codes,
            "is_chimera": True,
        },
        "energy_spent": FORCED_HYBRIDIZATION_COST,
        "energy_remaining": energy_service.get_state().current,
    }


# ========== 神力进阶系统 ==========

@router.get("/divine/status", tags=["divine"])
def get_divine_status() -> dict:
    """获取神力进阶系统完整状态"""
    from ..services.system.divine_progression import divine_progression_service
    return divine_progression_service.get_full_status()


@router.get("/divine/paths", tags=["divine"])
def get_available_paths() -> dict:
    """获取可选择的神格路线"""
    from ..services.system.divine_progression import divine_progression_service
    return {
        "paths": divine_progression_service.get_available_paths(),
        "current_path": divine_progression_service.get_path_info(),
    }


@router.post("/divine/path/choose", tags=["divine"])
def choose_divine_path(
    request: dict,
    _: None = Depends(require_not_running),
) -> dict:
    """选择神格路线（模拟运行时禁止）"""
    from ..services.system.divine_progression import divine_progression_service, DivinePath
    
    path_str = request.get("path", "")
    logger.info(f"[神格] 收到选择请求: {path_str}")
    
    try:
        path = DivinePath(path_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知的神格路线: {path_str}")
    
    if path == DivinePath.NONE:
        raise HTTPException(status_code=400, detail="请选择一个有效的神格")
    
    success, message = divine_progression_service.choose_path(path)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "success": True,
        "message": message,
        "path_info": divine_progression_service.get_path_info(),
    }


@router.get("/divine/skills", tags=["divine"])
def get_divine_skills() -> dict:
    """获取所有神力技能信息"""
    from ..services.system.divine_progression import divine_progression_service, DIVINE_SKILLS
    
    path_info = divine_progression_service.get_path_info()
    current_path = path_info["path"] if path_info else None
    
    all_skills = []
    for skill_id, skill in DIVINE_SKILLS.items():
        info = divine_progression_service.get_skill_info(skill_id)
        info["is_current_path"] = skill.path.value == current_path
        all_skills.append(info)
    
    return {
        "skills": all_skills,
        "current_path": current_path,
    }


@router.post("/divine/skill/use", tags=["divine"])
async def use_divine_skill(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """使用神力技能（模拟运行时禁止）"""
    from ..services.system.divine_progression import divine_progression_service, DIVINE_SKILLS
    from ..services.system.divine_energy import energy_service
    
    skill_id = request.get("skill_id", "")
    target = request.get("target")
    
    logger.info(f"[技能] 尝试使用: {skill_id}, 目标: {target}")
    
    if skill_id not in DIVINE_SKILLS:
        raise HTTPException(status_code=400, detail=f"未知的技能: {skill_id}")
    
    skill = DIVINE_SKILLS[skill_id]
    skill_info = divine_progression_service.get_skill_info(skill_id)
    
    path_info = divine_progression_service.get_path_info()
    if not path_info:
        raise HTTPException(status_code=400, detail="请先选择一个神格路线")
    
    if not skill_info["unlocked"]:
        raise HTTPException(status_code=400, detail=f"技能「{skill.name}」尚未解锁")
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    actual_cost = skill.cost
    
    if energy_service.get_state().current < actual_cost:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！{skill.name}需要 {actual_cost} 能量"
        )
    
    success, msg = energy_service.spend_fixed(actual_cost, current_turn, details=f"技能: {skill.name}")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    divine_progression_service.add_experience(actual_cost)
    
    result = {"effect": "executed", "details": f"技能「{skill.name}」已释放"}
    
    # 简化的技能效果处理
    species_repo = container.species_repository
    
    if skill_id == "life_shelter" and target:
        species = species_repo.get_by_lineage(target)
        if species:
            species.is_protected = True
            species.protection_turns = 999
            species_repo.upsert(species)
            result["details"] = f"「{species.common_name}」获得生命庇护"
    
    return {
        "success": True,
        "skill": skill.name,
        "cost": actual_cost,
        "result": result,
        "energy_remaining": energy_service.get_state().current,
    }


# ========== 信仰系统 ==========

@router.get("/divine/faith", tags=["divine"])
def get_faith_status() -> dict:
    """获取信仰系统状态"""
    from ..services.system.divine_progression import divine_progression_service
    return divine_progression_service.get_faith_summary()


@router.post("/divine/faith/add", tags=["divine"])
def add_follower(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """添加信徒"""
    from ..services.system.divine_progression import divine_progression_service
    
    lineage_code = request.get("lineage_code", "")
    if not lineage_code:
        raise HTTPException(status_code=400, detail="请提供物种代码")
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {lineage_code} 已灭绝")
    
    morph = species.morphology_stats or {}
    population = morph.get("population", 100000)
    trophic = species.trophic_level or 1
    
    success = divine_progression_service.add_follower(
        lineage_code, species.common_name, population, trophic
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="该物种已是信徒")
    
    return {
        "success": True,
        "message": f"「{species.common_name}」已成为信徒",
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


@router.post("/divine/faith/bless", tags=["divine"])
def bless_follower(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """显圣 - 赐福信徒"""
    from ..services.system.divine_progression import divine_progression_service
    from ..services.system.divine_energy import energy_service
    
    lineage_code = request.get("lineage_code", "")
    if not lineage_code:
        raise HTTPException(status_code=400, detail="请提供物种代码")
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    success, message, reward = divine_progression_service.bless_follower(
        lineage_code, current_turn
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "success": True,
        "message": message,
        "reward": reward,
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


@router.post("/divine/faith/sanctify", tags=["divine"])
def sanctify_species(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """圣化物种"""
    from ..services.system.divine_progression import divine_progression_service
    
    lineage_code = request.get("lineage_code", "")
    if not lineage_code:
        raise HTTPException(status_code=400, detail="请提供物种代码")
    
    species_repo = container.species_repository
    engine = container.simulation_engine
    
    species = species_repo.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    current_turn = engine.turn_counter
    success, message = divine_progression_service.sanctify_species(
        lineage_code, current_turn
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "success": True,
        "message": message,
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


# ========== 神迹系统 ==========

@router.get("/divine/miracles", tags=["divine"])
def get_miracles() -> dict:
    """获取神迹状态"""
    from ..services.system.divine_progression import divine_progression_service
    return divine_progression_service.get_miracle_summary()


@router.post("/divine/miracle/charge", tags=["divine"])
def charge_miracle(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """充能神迹（模拟运行时禁止）"""
    from ..services.system.divine_progression import divine_progression_service
    from ..services.system.divine_energy import energy_service
    
    miracle_id = request.get("miracle_id", "")
    amount = request.get("amount", 10)
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    if energy_service.get_state().current < amount:
        raise HTTPException(status_code=400, detail="能量不足")
    
    success, message = divine_progression_service.charge_miracle(
        miracle_id, amount, current_turn
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    energy_service.spend_fixed(amount, current_turn, details=f"神迹充能: {miracle_id}")
    
    return {
        "success": True,
        "message": message,
        "miracle_summary": divine_progression_service.get_miracle_summary(),
    }


@router.post("/divine/miracle/cancel", tags=["divine"])
def cancel_miracle(request: dict) -> dict:
    """取消神迹充能"""
    from ..services.system.divine_progression import divine_progression_service
    
    miracle_id = request.get("miracle_id", "")
    
    success, message, refund = divine_progression_service.cancel_miracle(miracle_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "success": True,
        "message": message,
        "refund": refund,
    }


@router.post("/divine/miracle/execute", tags=["divine"])
async def execute_miracle(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """执行神迹（模拟运行时禁止）"""
    from ..services.system.divine_progression import divine_progression_service
    
    miracle_id = request.get("miracle_id", "")
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    success, message, effect = divine_progression_service.execute_miracle(
        miracle_id, current_turn
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {
        "success": True,
        "message": message,
        "effect": effect,
        "miracle_summary": divine_progression_service.get_miracle_summary(),
    }


# ========== 预言赌局系统 ==========

@router.get("/divine/wagers", tags=["divine"])
def get_wagers() -> dict:
    """获取预言赌局状态"""
    from ..services.system.divine_progression import divine_progression_service
    return divine_progression_service.get_wager_summary()


@router.post("/divine/wager/place", tags=["divine"])
def place_wager(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """下注预言（模拟运行时禁止）"""
    from ..services.system.divine_progression import divine_progression_service
    from ..services.system.divine_energy import energy_service
    
    prediction_type = request.get("type", "")
    target = request.get("target", "")
    bet_amount = request.get("amount", 10)
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    if energy_service.get_state().current < bet_amount:
        raise HTTPException(status_code=400, detail="能量不足")
    
    success, message = divine_progression_service.place_wager(
        prediction_type, target, bet_amount, current_turn
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    energy_service.spend_fixed(bet_amount, current_turn, details=f"预言赌注")
    
    return {
        "success": True,
        "message": message,
        "wager_summary": divine_progression_service.get_wager_summary(),
    }


@router.post("/divine/wager/check", tags=["divine"])
def check_wager(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """检查预言结果"""
    from ..services.system.divine_progression import divine_progression_service
    from ..services.system.divine_energy import energy_service
    
    wager_id = request.get("wager_id", "")
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    species_repo = container.species_repository
    all_species = species_repo.list_species()
    
    game_state = {
        "turn": current_turn,
        "species": {sp.lineage_code: sp for sp in all_species},
    }
    
    success, message, reward = divine_progression_service.check_wager(
        wager_id, game_state, current_turn
    )
    
    if reward > 0:
        energy_service.add_energy(reward, f"预言成功奖励")
    
    return {
        "success": success,
        "message": message,
        "reward": reward,
        "wager_summary": divine_progression_service.get_wager_summary(),
    }

