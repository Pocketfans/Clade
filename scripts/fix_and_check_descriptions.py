#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查并修复物种描述"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.repositories.species_repository import species_repository
from app.core.seed import A_SCENARIO

# 检查种子数据
print("=" * 80)
print("种子数据描述长度：")
print("=" * 80)
for scenario in A_SCENARIO:
    print(f"{scenario['lineage_code']}: {len(scenario['description'])}字")
    print(f"描述前100字: {scenario['description'][:100]}...")
    print()

# 检查数据库数据
print("\n" + "=" * 80)
print("数据库中的描述长度：")
print("=" * 80)
species_list = species_repository.list_species()
for sp in species_list[:3]:
    print(f"{sp.lineage_code}: {len(sp.description)}字")
    print(f"完整描述: {sp.description}")
    print()

# 重新设置初始物种的完整描述
print("\n" + "=" * 80)
print("修复初始物种描述...")
print("=" * 80)
for scenario in A_SCENARIO:
    code = scenario['lineage_code']
    species = species_repository.get_by_lineage(code)
    if species and len(species.description) < 50:
        print(f"修复 {code}: {len(species.description)}字 -> {len(scenario['description'])}字")
        species.description = scenario['description']
        species_repository.upsert(species)

# 验证修复
print("\n" + "=" * 80)
print("验证修复后的描述：")
print("=" * 80)
for code in ['A1', 'B1', 'C1']:
    species = species_repository.get_by_lineage(code)
    if species:
        print(f"{code}: {len(species.description)}字")
        print(f"描述: {species.description[:100]}...")
        print()

