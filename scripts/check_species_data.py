#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查数据库中的物种数据"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.repositories.species_repository import species_repository

species_list = species_repository.list_species()

print(f"物种总数: {len(species_list)}\n")

for i, sp in enumerate(species_list[:10], 1):
    print(f"{i}. {sp.lineage_code}: {sp.common_name}")
    print(f"   拉丁名: {sp.latin_name}")
    print(f"   描述长度: {len(sp.description)}字")
    print(f"   描述: {sp.description[:100]}...")
    print(f"   创建回合: {sp.created_turn}")
    print(f"   父系: {sp.parent_code or '无'}")
    print()

