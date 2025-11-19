from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.species import Species
from ..models.environment import MapState, MapTile, HabitatPopulation
from ..repositories.species_repository import species_repository
from ..repositories.environment_repository import environment_repository
from ..repositories.history_repository import history_repository


class SaveManager:
    """管理游戏存档的保存和加载"""

    def __init__(self, saves_dir: str | Path) -> None:
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)

    def list_saves(self) -> list[dict[str, Any]]:
        """列出所有存档"""
        saves = []
        for save_dir in sorted(self.saves_dir.glob("save_*")):
            if not save_dir.is_dir():
                continue
            meta_path = save_dir / "metadata.json"
            if not meta_path.exists():
                continue
            
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                metadata["save_name"] = save_dir.name
                saves.append(metadata)
            except Exception as e:
                print(f"[存档管理器] 读取存档元数据失败: {save_dir.name}, {e}")
                continue
        
        # 按最后保存时间排序
        saves.sort(key=lambda s: s.get("last_saved", ""), reverse=True)
        return saves

    def create_save(self, save_name: str, scenario: str = "原初大陆") -> dict[str, Any]:
        """创建新存档"""
        print(f"[存档管理器] 创建新存档: {save_name}")
        
        # 生成存档文件夹名称
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in save_name if c.isalnum() or c in " _-")[:20]
        save_dir = self.saves_dir / f"save_{timestamp}_{safe_name}"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建元数据
        metadata = {
            "save_name": save_name,
            "scenario": scenario,
            "created_at": datetime.now().isoformat(),
            "last_saved": datetime.now().isoformat(),
            "turn_index": 0,
            "species_count": 0,
        }
        
        (save_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        print(f"[存档管理器] 存档创建成功: {save_dir.name}")
        return metadata

    def save_game(self, save_name: str, turn_index: int) -> Path:
        """保存当前游戏状态"""
        print(f"[存档管理器] 保存游戏: {save_name}, 回合={turn_index}")
        
        # 查找或创建存档目录
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            print(f"[存档管理器] 存档不存在，创建新存档")
            self.create_save(save_name)
            save_dir = self._find_save_dir(save_name)
        
        # 获取所有数据
        species_list = species_repository.list_species()
        map_tiles = environment_repository.list_tiles()
        map_state = environment_repository.get_state()
        history_logs = history_repository.list_turns(limit=1000)
        
        # 保存数据（包含完整地图）
        save_data = {
            "turn_index": turn_index,
            "saved_at": datetime.now().isoformat(),
            "species": [sp.model_dump(mode="json") for sp in species_list],
            "map_tiles": [tile.model_dump(mode="json") for tile in map_tiles],  # 保存地图地块
            "map_state": map_state.model_dump(mode="json") if map_state else None,
            "history_count": len(history_logs),
        }
        
        print(f"[存档管理器] 保存数据: {len(species_list)} 物种, {len(map_tiles)} 地块")
        
        (save_dir / "game_state.json").write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # 更新元数据
        metadata = json.loads((save_dir / "metadata.json").read_text(encoding="utf-8"))
        metadata["last_saved"] = datetime.now().isoformat()
        metadata["turn_index"] = turn_index
        metadata["species_count"] = len(species_list)
        
        (save_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        print(f"[存档管理器] 游戏保存成功: {save_dir.name}")
        return save_dir

    def load_game(self, save_name: str) -> dict[str, Any]:
        """加载游戏存档"""
        print(f"[存档管理器] 加载游戏: {save_name}")
        
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            raise FileNotFoundError(f"存档不存在: {save_name}")
        
        game_state_path = save_dir / "game_state.json"
        if not game_state_path.exists():
            raise FileNotFoundError(f"存档数据文件不存在: {save_name}")
        
        # 读取存档数据
        save_data = json.loads(game_state_path.read_text(encoding="utf-8"))
        
        print(f"[存档管理器] 加载数据: {len(save_data.get('species', []))} 物种, {len(save_data.get('map_tiles', []))} 地块")
        
        # 恢复物种数据到数据库
        for species_data in save_data.get("species", []):
            normalized = self._normalize_species_payload(species_data)
            species = Species(**normalized)
            species_repository.upsert(species)
        
        # 恢复地图地块
        if save_data.get("map_tiles"):
            print(f"[存档管理器] 恢复 {len(save_data['map_tiles'])} 个地块...")
            tiles = [MapTile(**tile_data) for tile_data in save_data["map_tiles"]]
            environment_repository.upsert_tiles(tiles)
        
        # 恢复地图状态
        if save_data.get("map_state"):
            map_state = MapState(**save_data["map_state"])
            environment_repository.save_state(map_state)
        
        print(f"[存档管理器] 游戏加载成功: {save_name}")
        return save_data

    def delete_save(self, save_name: str) -> bool:
        """删除存档"""
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            return False
        
        shutil.rmtree(save_dir)
        print(f"[存档管理器] 存档已删除: {save_name}")
        return True

    def _find_save_dir(self, save_name: str) -> Path | None:
        """查找存档目录"""
        # 如果是完整的文件夹名称
        direct_path = self.saves_dir / save_name
        if direct_path.exists():
            return direct_path
        
        # 搜索包含该名称的存档
        for save_dir in self.saves_dir.glob("save_*"):
            meta_path = save_dir / "metadata.json"
            if not meta_path.exists():
                continue
            
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                if metadata.get("save_name") == save_name:
                    return save_dir
            except:
                continue
        
        return None

    def _normalize_species_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure JSON decoded species fields match SQLModel expectations."""
        updated_at = payload.get("updated_at")
        if isinstance(updated_at, str):
            try:
                normalized = updated_at.replace("Z", "+00:00")
                payload["updated_at"] = datetime.fromisoformat(normalized)
            except ValueError:
                payload["updated_at"] = datetime.utcnow()
        return payload

