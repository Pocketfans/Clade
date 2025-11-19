#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时脚本：批量替换print为logging"""
import re
from pathlib import Path

def replace_prints_in_file(file_path: Path):
    """替换文件中的print为logger调用"""
    print(f"处理文件: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        original_content = content
        
        # 替换print为logger
        replacements = [
            (r'print\(f\"\[引擎\] ', 'logger.info(f\"'),
            (r'print\(f\"\[引擎警告\] ', 'logger.warning(f\"'),
            (r'print\(f\"\[引擎错误\] ', 'logger.error(f\"'),
            (r'print\(f\"\[灭绝\] ', 'logger.info(f\"[灭绝] '),
            (r'print\(f\"\[分化\] ', 'logger.info(f\"[分化] '),
            (r'print\(f\"\[分化检查\] ', 'logger.debug(f\"[分化检查] '),
            (r'print\(f\"\[分化警告\] ', 'logger.warning(f\"[分化警告] '),
            (r'print\(f\"\[分化AI调用\] ', 'logger.debug(f\"[分化AI调用] '),
            (r'print\(f\"\[分化AI警告\] ', 'logger.warning(f\"[分化AI警告] '),
            (r'print\(f\"\[分化AI错误\] ', 'logger.error(f\"[分化AI错误] '),
            (r'print\(f\"\[器官演化\] ', 'logger.info(f\"[器官演化] '),
            (r'print\(f\"\[防重名\] ', 'logger.debug(f\"[防重名] '),
            (r'print\(f\"\[基因库\] ', 'logger.info(f\"[基因库] '),
            (r'print\(f\"\[基因遗传\] ', 'logger.info(f\"[基因遗传] '),
            (r'print\(f\"\[环境初始化\] ', 'logger.info(f\"[环境初始化] '),
            (r'print\(f\"\[环境初始化错误\] ', 'logger.error(f\"[环境初始化错误] '),
            (r'print\(f\"\[推演开始\] ', 'logger.info(f\"[推演开始] '),
            (r'print\(f\"\[推演执行\] ', 'logger.debug(f\"[推演执行] '),
            (r'print\(f\"\[推演完成\] ', 'logger.info(f\"[推演完成] '),
            (r'print\(f\"\[推演错误\] ', 'logger.error(f\"[推演错误] '),
            (r'print\(f\"\[存档API\] ', 'logger.info(f\"[存档API] '),
            (r'print\(f\"\[存档API错误\] ', 'logger.error(f\"[存档API错误] '),
            (r'print\(f\"\[物种生成API错误\] ', 'logger.error(f\"[物种生成API错误] '),
            (r'print\(f\"\[测试 Embedding\] ', 'logger.debug(f\"[测试 Embedding] '),
            (r'print\(f\"\[地图查询\] ', 'logger.debug(f\"[地图查询] '),
            (r'print\(f\"\[地图查询错误\] ', 'logger.error(f\"[地图查询错误] '),
            (r'print\(f\"\[配置\] ', 'logger.info(f\"[配置] '),
        ]
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        # 特殊处理：替换简单的print语句
        content = re.sub(r'print\(traceback\.format_exc\(\)\)', '', content)
        
        # 只在内容发生变化时写入
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] Updated: {file_path}")
            return True
        else:
            print(f"[SKIP] No changes: {file_path}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Processing {file_path}: {e}")
        return False

# 需要处理的文件列表
files_to_process = [
    Path("../backend/app/simulation/engine.py"),
    Path("../backend/app/services/speciation.py"),
    Path("../backend/app/api/routes.py"),
    Path("../backend/app/services/gene_library.py"),
    Path("../backend/app/core/database.py"),
]

print("开始批量替换print为logger...")
print("="*60)

updated_count = 0
for file_path in files_to_process:
    if file_path.exists():
        if replace_prints_in_file(file_path):
            updated_count += 1
    else:
        print(f"[NOT FOUND] File: {file_path}")

print("="*60)
print(f"Done! Updated {updated_count}/{len(files_to_process)} files")

