#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EvoSandbox 系统健康检查工具

功能：
1. 检查后端 API 服务是否在线。
2. 检查数据库连接与关键数据完整性。
3. 检查关键目录权限与存在性。
4. 验证初始物种数据是否符合 Schema。

用法：
    python scripts/health_check.py
"""

import sys
import os
import httpx
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.core.config import get_settings
from app.repositories.species_repository import species_repository

settings = get_settings()
BASE_URL = "http://localhost:8000"

def check_api_connectivity():
    """检查 API 服务连通性"""
    print(f"检查 API 服务 ({BASE_URL})... ", end="", flush=True)
    try:
        # 尝试访问一个简单的端点，如列出存档
        response = httpx.get(f"{BASE_URL}/api/saves/list", timeout=5.0)
        if response.status_code == 200:
            print("[OK]")
            return True
        else:
            print(f"[FAIL] 状态码: {response.status_code}")
            return False
    except httpx.ConnectError:
        print("[FAIL] 无法连接 (服务未启动?)")
        return False
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def check_database_integrity():
    """检查数据库完整性"""
    print("检查数据库完整性... ", end="", flush=True)
    try:
        # 1. 检查初始物种
        initial_codes = ['A1', 'B1', 'C1']
        missing = []
        for code in initial_codes:
            sp = species_repository.get_by_lineage(code)
            if not sp:
                missing.append(code)
        
        if missing:
            print(f"[FAIL] 缺失初始物种: {missing}")
            return False
            
        # 2. 检查物种数据字段
        sp = species_repository.get_by_lineage('A1')
        if not sp.description or len(sp.description) < 10:
            print("[FAIL] 初始物种描述异常")
            return False
            
        print("[OK]")
        return True
    except Exception as e:
        print(f"[FAIL] 数据库错误: {e}")
        return False

def check_directories():
    """检查关键目录"""
    print("检查数据目录结构... ", end="", flush=True)
    required_dirs = [
        "data/db",
        "data/logs",
        "data/reports",
        "data/saves",
        "data/exports"
    ]
    
    root_dir = Path(__file__).parent.parent
    missing = []
    
    for d in required_dirs:
        path = root_dir / d
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                print(f"(创建 {d}) ", end="")
            except Exception:
                missing.append(d)
    
    if missing:
        print(f"[FAIL] 无法创建目录: {missing}")
        return False
    
    print("[OK]")
    return True

def main():
    print("=" * 60)
    print("EvoSandbox 系统健康检查")
    print("=" * 60)
    
    results = []
    
    # 1. 目录检查
    results.append(check_directories())
    
    # 2. 数据库检查
    results.append(check_database_integrity())
    
    # 3. API 检查
    results.append(check_api_connectivity())
    
    print("-" * 60)
    if all(results):
        print("✅ 系统状态良好")
        sys.exit(0)
    else:
        print("❌ 系统存在问题，请检查上述错误日志")
        # 如果 API 失败，提示启动命令
        if not results[2]:
            print("\n提示: 请确保后端服务已启动:")
            print("  uvicorn backend.app.main:app --reload --port 8000")
        sys.exit(1)

if __name__ == "__main__":
    main()

