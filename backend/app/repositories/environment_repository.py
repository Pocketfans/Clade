from __future__ import annotations

import logging
from collections.abc import Iterable

from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)
from sqlalchemy.sql import func
from sqlmodel import select

from ..core.database import session_scope
from ..models.environment import (
    EnvironmentEvent,
    HabitatPopulation,
    MapState,
    MapTile,
)
from ..models.config import UIConfig, ProviderConfig


class EnvironmentRepository:
    def upsert_tiles(self, tiles: Iterable[MapTile]) -> None:
        with session_scope() as session:
            for tile in tiles:
                session.merge(tile)

    def list_tiles(self, limit: int | None = None) -> list[MapTile]:
        with session_scope() as session:
            stmt = select(MapTile)
            if limit:
                stmt = stmt.limit(limit)
            return list(session.exec(stmt))

    def log_event(self, event: EnvironmentEvent) -> EnvironmentEvent:
        with session_scope() as session:
            session.add(event)
            session.flush()
            session.refresh(event)
            return event

    def get_state(self) -> MapState | None:
        with session_scope() as session:
            return session.exec(select(MapState)).first()

    def save_state(self, state: MapState) -> MapState:
        with session_scope() as session:
            merged = session.merge(state)
            session.flush()
            session.refresh(merged)
            return merged

    def clear_state(self) -> None:
        """清除所有环境相关数据（用于读档前）"""
        with session_scope() as session:
            # 先删除依赖表
            session.exec(text("DELETE FROM habitat_populations"))
            session.exec(text("DELETE FROM environment_events"))
            # 再删除主表
            session.exec(text("DELETE FROM map_tiles"))
            session.exec(text("DELETE FROM map_state"))

    def ensure_tile_columns(self) -> None:
        with session_scope() as session:
            info = session.exec(text("PRAGMA table_info('map_tiles')")).all()
            if not info:
                return
            columns = {row[1] for row in info}
            if "q" not in columns:
                session.exec(text("ALTER TABLE map_tiles ADD COLUMN q INTEGER DEFAULT 0"))
            if "r" not in columns:
                session.exec(text("ALTER TABLE map_tiles ADD COLUMN r INTEGER DEFAULT 0"))
            if "salinity" not in columns:
                print("[环境仓储] 添加 salinity 列...")
                session.exec(text("ALTER TABLE map_tiles ADD COLUMN salinity REAL DEFAULT 35.0"))
            if "is_lake" not in columns:
                print("[环境仓储] 添加 is_lake 列...")
                session.exec(text("ALTER TABLE map_tiles ADD COLUMN is_lake BOOLEAN DEFAULT 0"))
    
    def ensure_map_state_columns(self) -> None:
        """确保 map_state 表包含海平面和温度字段"""
        with session_scope() as session:
            info = session.exec(text("PRAGMA table_info('map_state')")).all()
            if not info:
                return
            columns = {row[1] for row in info}
            if "sea_level" not in columns:
                print("[环境仓储] 添加 sea_level 列...")
                session.exec(text("ALTER TABLE map_state ADD COLUMN sea_level REAL DEFAULT 0.0"))
            if "global_avg_temperature" not in columns:
                print("[环境仓储] 添加 global_avg_temperature 列...")
                session.exec(text("ALTER TABLE map_state ADD COLUMN global_avg_temperature REAL DEFAULT 15.0"))
            if "map_seed" not in columns:
                print("[环境仓储] 添加 map_seed 列...")
                session.exec(text("ALTER TABLE map_state ADD COLUMN map_seed INTEGER DEFAULT NULL"))

    def load_ui_config(self, path: Path) -> UIConfig:
        """仅从 JSON 文件加载 UI 配置"""
        # 1. 从 JSON 文件加载
        if path.exists():
            config = UIConfig.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            config = UIConfig()
        return config

    def save_ui_config(self, path: Path, config: UIConfig) -> UIConfig:
        """保存 UI 配置到 JSON 文件"""
        # 1. 保存到 JSON 文件
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug(f"[配置] 已保存配置到 {path}")
        return config

    def list_habitats(self) -> list[HabitatPopulation]:
        with session_scope() as session:
            return list(session.exec(select(HabitatPopulation)))

    def write_habitats(self, habitats: Iterable[HabitatPopulation]) -> None:
        with session_scope() as session:
            for habitat in habitats:
                session.add(habitat)

    def latest_habitats(
        self,
        species_ids: list[int] | None = None,
        limit: int | None = None,
        per_species_latest: bool = True,
    ) -> list[HabitatPopulation]:
        """获取最新的栖息地记录
        
        Args:
            species_ids: 可选，只获取指定物种的记录
            limit: 可选，限制返回数量
            per_species_latest: 【改进】如果为True，对每个物种取其最新turn的记录；
                               如果为False，取全局max_turn的记录（旧行为）
        
        Returns:
            list[HabitatPopulation]: 栖息地记录列表
        """
        with session_scope() as session:
            if not per_species_latest:
                # 旧逻辑：只取全局 max_turn
                max_turn = session.exec(select(func.max(HabitatPopulation.turn_index))).one()
                if max_turn is None:
                    return []
                stmt = (
                    select(HabitatPopulation)
                    .where(HabitatPopulation.turn_index == max_turn)
                    .order_by(HabitatPopulation.population.desc())
                )
                if species_ids:
                    stmt = stmt.where(HabitatPopulation.species_id.in_(species_ids))
                if limit:
                    stmt = stmt.limit(limit)
                return list(session.exec(stmt))
            
            # 【改进】新逻辑：对每个物种取其最新 turn_index 的记录
            # 这样即使某物种在当前回合没有写入新记录，也能取到它最近一次的栖息地数据
            
            # 子查询：获取每个物种的最新 turn_index
            from sqlmodel import col
            subquery = (
                select(
                    HabitatPopulation.species_id,
                    func.max(HabitatPopulation.turn_index).label("max_turn")
                )
                .group_by(HabitatPopulation.species_id)
            )
            if species_ids:
                subquery = subquery.where(HabitatPopulation.species_id.in_(species_ids))
            subquery = subquery.subquery()
            
            # 主查询：关联子查询获取每个物种最新回合的所有记录
            stmt = (
                select(HabitatPopulation)
                .join(
                    subquery,
                    (HabitatPopulation.species_id == subquery.c.species_id) &
                    (HabitatPopulation.turn_index == subquery.c.max_turn)
                )
                .order_by(HabitatPopulation.population.desc())
            )
            if limit:
                stmt = stmt.limit(limit)
            return list(session.exec(stmt))
    
    def get_species_with_habitats(self, current_turn_only: bool = False) -> set[int]:
        """获取所有有栖息地记录的物种ID集合
        
        Args:
            current_turn_only: 如果为True，只返回最新回合有记录的物种；
                              如果为False，返回所有有过栖息地记录的物种（默认）
        
        Returns:
            set[int]: 有栖息地记录的物种ID集合
        """
        with session_scope() as session:
            if current_turn_only:
                # 旧逻辑：只看全局 max_turn
                max_turn = session.exec(select(func.max(HabitatPopulation.turn_index))).one()
                if max_turn is None:
                    return set()
                stmt = select(HabitatPopulation.species_id).where(HabitatPopulation.turn_index == max_turn).distinct()
            else:
                # 【改进】返回所有有过栖息地记录的物种（不限制回合）
                stmt = select(HabitatPopulation.species_id).distinct()
            result = session.exec(stmt).all()
            return set(result)
    
    def get_habitats_by_species_id(self, species_id: int, latest_only: bool = True) -> list[HabitatPopulation]:
        """获取指定物种的栖息地记录（用于分化时继承栖息地）
        
        Args:
            species_id: 物种ID
            latest_only: 是否只获取该物种最新回合的记录（默认True）
                        【改进】现在取的是该物种自己的最新turn，而非全局max_turn
            
        Returns:
            list[HabitatPopulation]: 该物种的栖息地记录列表
        """
        with session_scope() as session:
            if latest_only:
                # 【改进】取该物种自己的最新 turn_index，而非全局 max_turn
                species_max_turn = session.exec(
                    select(func.max(HabitatPopulation.turn_index))
                    .where(HabitatPopulation.species_id == species_id)
                ).one()
                if species_max_turn is None:
                    return []
                stmt = (
                    select(HabitatPopulation)
                    .where(HabitatPopulation.species_id == species_id)
                    .where(HabitatPopulation.turn_index == species_max_turn)
                )
            else:
                stmt = select(HabitatPopulation).where(HabitatPopulation.species_id == species_id)
            return list(session.exec(stmt))

    def get_tile_coordinates_map(self) -> dict[int, tuple[int, int]]:
        """获取所有地块的坐标映射 {tile_id: (x, y)}
        
        用于批量处理物种迁移时的坐标查找
        """
        with session_scope() as session:
            # 只查询需要的列
            stmt = select(MapTile.id, MapTile.x, MapTile.y)
            results = session.exec(stmt).all()
            return {row[0]: (row[1], row[2]) for row in results if row[0] is not None}



# DEPRECATED: Module-level singleton
# Use container.environment_repository instead for proper isolation.
# This global instance will be removed in a future version.
environment_repository = EnvironmentRepository()
