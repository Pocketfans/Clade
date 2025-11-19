#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""最终验证：确认所有修复已生效"""

import sys
import os
import httpx
import time

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.repositories.species_repository import species_repository

BASE_URL = "http://localhost:8000"

def verify_system():
    """验证系统状态"""
    print("=" * 80)
    print("EvoSandbox 最终验证")
    print("=" * 80)
    
    checks = []
    
    # 1. 检查初始物种描述完整性
    print("\n1. 初始物种描述完整性")
    print("-" * 80)
    
    initial_species = ['A1', 'B1', 'C1']
    desc_ok = True
    for code in initial_species:
        sp = species_repository.get_by_lineage(code)
        if sp:
            desc_len = len(sp.description)
            print(f"{code}: {sp.common_name}")
            print(f"  描述长度: {desc_len}字")
            print(f"  拉丁名: {sp.latin_name}")
            
            if desc_len >= 100:
                print(f"  [OK] 描述详细完整")
            else:
                print(f"  [FAIL] 描述过短")
                desc_ok = False
        else:
            print(f"[FAIL] 缺少{code}")
            desc_ok = False
    
    checks.append(("初始物种描述完整", desc_ok))
    
    # 2. 分化条件严格性（运行低压力测试）
    print("\n2. 分化条件严格性（低压力测试）")
    print("-" * 80)
    print("运行3回合低压力（4.0）推演...")
    
    speciation_ok = True
    try:
        response = httpx.post(
            f"{BASE_URL}/api/turns/run",
            json={
                "rounds": 3,
                "pressures": [{"kind": "temperature", "intensity": 4.0, "narrative": "低压力"}]
            },
            timeout=120
        )
        
        if response.status_code == 200:
            reports = response.json()
            total_branching = sum(len(r.get("branching_events", [])) for r in reports)
            print(f"总分化事件: {total_branching}")
            
            if total_branching <= 1:
                print("[OK] 低压力下分化频率合理（≤1）")
            else:
                print(f"[WARN] 低压力下分化过多（{total_branching}次）")
                speciation_ok = False
        else:
            print(f"[FAIL] 推演失败: {response.status_code}")
            speciation_ok = False
    except Exception as e:
        print(f"[FAIL] 错误: {str(e)}")
        speciation_ok = False
    
    checks.append(("分化条件严格", speciation_ok))
    
    # 3. 死亡率合理性
    print("\n3. 死亡率合理性")
    print("-" * 80)
    
    death_rate_ok = False
    if response.status_code == 200:
        reports = response.json()
        if reports:
            last_report = reports[-1]
            death_rates = [s["death_rate"] for s in last_report.get("species", [])[:10]]
            
            if death_rates:
                avg_death = sum(death_rates) / len(death_rates)
                max_death = max(death_rates)
                
                print(f"平均死亡率: {avg_death*100:.1f}%")
                print(f"最高死亡率: {max_death*100:.1f}%")
                
                if avg_death <= 0.3 and max_death <= 0.5:
                    print("[OK] 死亡率在合理范围内")
                    death_rate_ok = True
                else:
                    print("[WARN] 死亡率偏高")
    
    checks.append(("死亡率合理", death_rate_ok))
    
    # 4. 报告质量
    print("\n4. 报告文件检查")
    print("-" * 80)
    from pathlib import Path
    
    reports_dir = Path("../data/reports")
    report_ok = False
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("turn_*.md"))
        if report_files:
            latest = report_files[-1]
            content = latest.read_text(encoding="utf-8")
            
            print(f"最新报告: {latest.name}")
            
            # 检查关键标记
            has_desc = "描述:" in content
            has_species = "物种列表" in content or "种群" in content
            
            print(f"  包含描述: {'是' if has_desc else '否'}")
            print(f"  包含物种数据: {'是' if has_species else '否'}")
            
            if has_desc and has_species:
                print("[OK] 报告结构完整")
                report_ok = True
            else:
                print("[WARN] 报告可能不完整")
        else:
            print("[WARN] 未找到报告文件")
    
    checks.append(("报告文件完整", report_ok))
    
    # 总结
    print("\n" + "=" * 80)
    print("验证总结")
    print("=" * 80)
    
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    
    for name, result in checks:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print("-" * 80)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n[SUCCESS] 所有验证通过！系统运行正常。")
        return True
    else:
        print(f"\n[WARNING] 部分验证未通过，建议检查。")
        return False


if __name__ == "__main__":
    try:
        success = verify_system()
        print("\n" + "=" * 80)
        print("验证完成")
        print("=" * 80 + "\n")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n严重错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

