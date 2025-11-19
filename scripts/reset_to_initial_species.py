#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重置为初始三个物种，删除所有分化物种"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.repositories.species_repository import species_repository
from app.core.seed import A_SCENARIO
from app.models.species import Species

# 获取所有物种
all_species = species_repository.list_species()
initial_codes = {s['lineage_code'] for s in A_SCENARIO}

print(f"当前物种总数: {len(all_species)}")
print(f"初始物种: {initial_codes}")
print()

# 确保初始物种的描述是完整的
print("=" * 80)
print("确保初始物种描述完整...")
print("=" * 80)
for scenario in A_SCENARIO:
    species = species_repository.get_by_lineage(scenario['lineage_code'])
    if species:
        species.description = scenario['description']
        species.latin_name = scenario['latin_name']
        species.common_name = scenario['common_name']
        species.morphology_stats = scenario['morphology_stats']
        species.abstract_traits = scenario['abstract_traits']
        species.hidden_traits = scenario['hidden_traits']
        species.parent_code = None
        species.created_turn = 0
        species.status = 'alive'
        species_repository.upsert(species)
        print(f"[OK] {species.lineage_code}: {len(species.description)}字")

# 删除所有非初始物种
print("\n" + "=" * 80)
print("删除分化物种...")
print("=" * 80)
deleted_count = 0
for species in all_species:
    if species.lineage_code not in initial_codes:
        print(f"删除: {species.lineage_code} ({species.common_name})")
        from app.core.database import session_scope
        with session_scope() as session:
            session.delete(species)
        deleted_count += 1

print(f"\n已删除 {deleted_count} 个分化物种")

# 验证最终状态
remaining = species_repository.list_species()
print(f"\n最终物种数: {len(remaining)}")
for sp in remaining:
    print(f"  {sp.lineage_code}: {sp.common_name} ({len(sp.description)}字)")

