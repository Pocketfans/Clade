"""快速验证预算系统功能"""
import sys
sys.path.insert(0, 'backend')

from app.services.species.trait_config import (
    get_single_trait_cap,
    get_diminishing_factor,
    get_diminishing_summary,
    get_breakthrough_summary,
    get_bonus_summary,
    get_habitat_trait_bonus,
    get_effective_trait_cap,
    TraitConfig,
)

def main():
    print("=" * 60)
    print("属性预算系统功能验证")
    print("=" * 60)
    
    # 1. 测试单属性上限
    print("\n【1. 单属性上限测试】")
    for turn in [0, 100, 500, 1000, 2000]:
        cap = get_single_trait_cap(turn, trophic_level=2.0)
        print(f"  回合{turn}: 单属性上限 = {cap}")
    
    # 2. 测试边际递减
    print("\n【2. 边际递减测试】")
    turn = 500
    cap = get_single_trait_cap(turn)
    print(f"  基准: 回合{turn}, 上限{cap}")
    for ratio in [0.3, 0.5, 0.6, 0.75, 0.9, 0.98]:
        value = cap * ratio
        factor = get_diminishing_factor(value, turn)
        print(f"  属性值{value:.1f} ({ratio:.0%}上限): 效率{factor:.0%}")
    
    # 3. 测试边际递减摘要
    print("\n【3. 边际递减摘要测试】")
    traits = {
        "耐寒性": cap * 0.8,
        "耐热性": cap * 0.55,
        "运动能力": cap * 0.3,
        "繁殖速度": cap * 0.45,
    }
    summary = get_diminishing_summary(traits, turn)
    print(f"  高属性数量: {len(summary['high_traits'])}")
    if summary['warning_text']:
        print(f"  警告: {summary['warning_text'][:200]}")
    if summary['strategy_hint']:
        print(f"  建议: {summary['strategy_hint']}")
    
    # 4. 测试突破系统
    print("\n【4. 突破系统测试】")
    breakthrough = get_breakthrough_summary(traits, turn)
    print(f"  已达成突破: {len(breakthrough['achieved'])}")
    for a in breakthrough['achieved']:
        print(f"    - {a['trait']}: 「{a['tier']}」")
    print(f"  接近突破: {len(breakthrough['near'])}")
    for n in breakthrough['near'][:3]:
        print(f"    - {n['trait']}: 差{n['gap']:.1f}达「{n['tier_name']}」")
    
    # 5. 测试栖息地加成
    print("\n【5. 栖息地加成测试】")
    for habitat in ["deep_sea", "aerial", "terrestrial"]:
        bonus = get_habitat_trait_bonus(habitat)
        print(f"  {habitat}: {dict(list(bonus.items())[:3])}")
    
    # 6. 测试有效上限
    print("\n【6. 有效上限测试（含加成）】")
    base = get_single_trait_cap(turn)
    effective = get_effective_trait_cap(
        "耐高压", turn, 2.0, 
        habitat_type="deep_sea"
    )
    print(f"  基础上限: {base}")
    print(f"  有效上限(耐高压+深海): {effective}")
    print(f"  加成: +{effective - base}")
    
    # 7. 测试加成摘要
    print("\n【7. 加成摘要测试】")
    organs = {"sensory": {"stage": 3}, "locomotion": {"stage": 2}}
    bonus_summary = get_bonus_summary("marine", organs)
    print(f"  栖息地加成: {bonus_summary['habitat_bonus']}")
    print(f"  器官加成: {bonus_summary['organ_bonus']}")
    
    print("\n" + "=" * 60)
    print("✅ 所有功能验证完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
