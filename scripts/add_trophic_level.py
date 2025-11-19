"""数据库迁移：为Species表添加trophic_level字段并计算初始值"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.core.database import session_scope
from app.models.species import Species
from app.services.trophic import TrophicLevelCalculator
from sqlalchemy import text

def migrate():
    """添加trophic_level字段并计算初始值"""
    calculator = TrophicLevelCalculator()
    
    with session_scope() as session:
        # 1. 检查字段是否已存在
        result = session.execute(text("PRAGMA table_info(species)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "trophic_level" not in columns:
            print("添加trophic_level字段...")
            session.execute(text("ALTER TABLE species ADD COLUMN trophic_level REAL DEFAULT 1.0"))
            session.commit()
            print("[OK] 字段添加成功")
        else:
            print("trophic_level字段已存在")
        
        # 2. 计算所有现有物种的营养级
        print("\n计算物种营养级...")
        species_list = session.query(Species).all()
        
        for species in species_list:
            trophic = calculator.calculate_trophic_level(species, species_list)
            species.trophic_level = trophic
            category = calculator.get_trophic_category(trophic)
            print(f"  {species.common_name} ({species.lineage_code}): T={trophic:.2f} ({category})")
        
        session.commit()
        print(f"\n[OK] 已更新 {len(species_list)} 个物种的营养级")
        
        # 3. 统计
        print("\n营养级分布统计：")
        for category in ["生产者/分解者", "主要草食", "中层捕食者", "高层捕食者", "顶级掠食者"]:
            count = sum(1 for s in species_list if calculator.get_trophic_category(s.trophic_level) == category)
            print(f"  {category}: {count}个")

if __name__ == "__main__":
    migrate()

