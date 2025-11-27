from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ...models.species import Species
from ...models.environment import MapState, MapTile, HabitatPopulation
from ...models.history import TurnLog
from ...repositories.species_repository import species_repository
from ...repositories.environment_repository import environment_repository
from ...repositories.history_repository import history_repository

if TYPE_CHECKING:
    from .embedding import EmbeddingService


class SaveManager:
    """管理游戏存档的保存和加载
    
    【重要改进】
    1. 支持保存和恢复 embedding 数据
    2. 支持保存分类学数据（Clade）
    3. 支持保存事件 embedding 索引
    """

    def __init__(
        self, 
        saves_dir: str | Path,
        embedding_service: 'EmbeddingService | None' = None
    ) -> None:
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        self._embedding_service = embedding_service

    def set_embedding_service(self, service: 'EmbeddingService') -> None:
        """设置 embedding 服务（延迟注入）"""
        self._embedding_service = service

    def list_saves(self) -> list[dict[str, Any]]:
        """列出所有存档"""
        saves = []
        for save_dir in sorted(self.saves_dir.glob("save_*")):
            if not save_dir.is_dir():
                continue
            meta_path = save_dir / "metadata.json"
            game_state_path = save_dir / "game_state.json"
            
            if not meta_path.exists() or not game_state_path.exists():
                continue
            
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                
                # Convert to frontend-friendly format
                last_saved_iso = metadata.get("last_saved", "")
                try:
                    dt = datetime.fromisoformat(last_saved_iso)
                    timestamp = dt.timestamp()
                except ValueError:
                    timestamp = 0
                
                # 检查是否有 embedding 数据
                has_embeddings = (save_dir / "embeddings.json").exists()
                has_taxonomy = (save_dir / "taxonomy.json").exists()
                
                formatted_save = {
                    "name": metadata.get("save_name", save_dir.name),
                    "turn": metadata.get("turn_index", 0),
                    "species_count": metadata.get("species_count", 0),
                    "timestamp": timestamp,
                    "scenario": metadata.get("scenario", "Unknown"),
                    "has_embeddings": has_embeddings,
                    "has_taxonomy": has_taxonomy,
                    # Keep original fields just in case
                    "save_name": metadata.get("save_name", save_dir.name),
                    "turn_index": metadata.get("turn_index", 0),
                    "last_saved": last_saved_iso
                }
                saves.append(formatted_save)
            except Exception as e:
                print(f"[存档管理器] 读取存档元数据失败: {save_dir.name}, {e}")
                continue
        
        # 按最后保存时间排序
        saves.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
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

    def save_game(
        self, 
        save_name: str, 
        turn_index: int,
        taxonomy_data: dict[str, Any] | None = None,
        event_embeddings: dict[str, Any] | None = None,
    ) -> Path:
        """保存当前游戏状态
        
        Args:
            save_name: 存档名称
            turn_index: 当前回合数
            taxonomy_data: 分类学数据（可选）
            event_embeddings: 事件 embedding 数据（可选）
        
        Returns:
            存档目录路径
        """
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
        habitats = environment_repository.list_habitats()
        history_logs = history_repository.list_turns(limit=1000)
        
        # 保存数据（包含完整地图）
        save_data = {
            "turn_index": turn_index,
            "saved_at": datetime.now().isoformat(),
            "species": [sp.model_dump(mode="json") for sp in species_list],
            "map_tiles": [tile.model_dump(mode="json") for tile in map_tiles],
            "habitats": [h.model_dump(mode="json") for h in habitats],
            "map_state": map_state.model_dump(mode="json") if map_state else None,
            "history_logs": [log.model_dump(mode="json") for log in history_logs],
            "history_count": len(history_logs),
        }
        
        print(f"[存档管理器] 保存数据: {len(species_list)} 物种, {len(map_tiles)} 地块, {len(habitats)} 栖息地, {len(history_logs)} 历史记录")
        
        (save_dir / "game_state.json").write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # ========== 保存 Embedding 数据 ==========
        if self._embedding_service and species_list:
            try:
                descriptions = [sp.description for sp in species_list]
                embedding_data = self._embedding_service.export_embeddings(descriptions)
                embedding_data["species_count"] = len(species_list)
                embedding_data["saved_at"] = datetime.now().isoformat()
                
                (save_dir / "embeddings.json").write_text(
                    json.dumps(embedding_data, ensure_ascii=False),
                    encoding="utf-8"
                )
                print(f"[存档管理器] 已保存 {len(embedding_data.get('embeddings', {}))} 个 embedding 向量")
            except Exception as e:
                print(f"[存档管理器] 保存 embedding 数据失败: {e}")
        
        # ========== 保存分类学数据 ==========
        if taxonomy_data:
            try:
                (save_dir / "taxonomy.json").write_text(
                    json.dumps(taxonomy_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"[存档管理器] 已保存分类学数据")
            except Exception as e:
                print(f"[存档管理器] 保存分类学数据失败: {e}")
        
        # ========== 保存事件 Embedding ==========
        if event_embeddings:
            try:
                (save_dir / "event_embeddings.json").write_text(
                    json.dumps(event_embeddings, ensure_ascii=False),
                    encoding="utf-8"
                )
                print(f"[存档管理器] 已保存事件 embedding 数据")
            except Exception as e:
                print(f"[存档管理器] 保存事件 embedding 失败: {e}")
        
        # 更新元数据
        metadata = json.loads((save_dir / "metadata.json").read_text(encoding="utf-8"))
        metadata["last_saved"] = datetime.now().isoformat()
        metadata["turn_index"] = turn_index
        metadata["species_count"] = len(species_list)
        metadata["has_embeddings"] = (save_dir / "embeddings.json").exists()
        metadata["has_taxonomy"] = (save_dir / "taxonomy.json").exists()
        
        (save_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        print(f"[存档管理器] 游戏保存成功: {save_dir.name}")
        return save_dir

    def load_game(self, save_name: str) -> dict[str, Any]:
        """加载游戏存档
        
        Returns:
            包含以下键的字典:
            - turn_index, species, map_tiles, habitats, map_state, history_logs
            - embeddings_loaded: bool - 是否成功加载了 embedding
            - taxonomy: dict | None - 分类学数据
            - event_embeddings: dict | None - 事件 embedding 数据
        """
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
        
        # 1. 清除当前运行时数据
        print("[存档管理器] 清除当前运行时状态...")
        environment_repository.clear_state()
        species_repository.clear_state()
        history_repository.clear_state()

        # 恢复物种数据到数据库
        restored_species = []
        for species_data in save_data.get("species", []):
            normalized = self._normalize_species_payload(species_data)
            species = Species(**normalized)
            species_repository.upsert(species)
            restored_species.append(species)
        
        # 恢复地图地块
        if save_data.get("map_tiles"):
            print(f"[存档管理器] 恢复 {len(save_data['map_tiles'])} 个地块...")
            tiles = [MapTile(**tile_data) for tile_data in save_data["map_tiles"]]
            environment_repository.upsert_tiles(tiles)
        
        # 恢复地图状态
        if save_data.get("map_state"):
            map_state = MapState(**save_data["map_state"])
            environment_repository.save_state(map_state)

        # 恢复栖息地分布
        if save_data.get("habitats"):
            print(f"[存档管理器] 恢复 {len(save_data['habitats'])} 个栖息地记录...")
            habitats = [HabitatPopulation(**h_data) for h_data in save_data["habitats"]]
            environment_repository.write_habitats(habitats)

        # 恢复历史记录
        if save_data.get("history_logs"):
            print(f"[存档管理器] 恢复 {len(save_data['history_logs'])} 条历史记录...")
            for log_data in save_data["history_logs"]:
                if isinstance(log_data.get("created_at"), str):
                     try:
                        log_data["created_at"] = datetime.fromisoformat(log_data["created_at"].replace("Z", "+00:00"))
                     except ValueError:
                        pass
                log = TurnLog(**log_data)
                history_repository.log_turn(log)
        
        # ========== 恢复 Embedding 数据 ==========
        embeddings_loaded = False
        embeddings_path = save_dir / "embeddings.json"
        if embeddings_path.exists() and self._embedding_service:
            try:
                embedding_data = json.loads(embeddings_path.read_text(encoding="utf-8"))
                descriptions = [sp.description for sp in restored_species]
                imported = self._embedding_service.import_embeddings(embedding_data, descriptions)
                embeddings_loaded = imported > 0
                print(f"[存档管理器] 已恢复 {imported} 个 embedding 向量")
            except Exception as e:
                print(f"[存档管理器] 恢复 embedding 数据失败: {e}")
        
        save_data["embeddings_loaded"] = embeddings_loaded
        
        # ========== 加载分类学数据 ==========
        taxonomy_path = save_dir / "taxonomy.json"
        if taxonomy_path.exists():
            try:
                save_data["taxonomy"] = json.loads(taxonomy_path.read_text(encoding="utf-8"))
                print(f"[存档管理器] 已加载分类学数据")
            except Exception as e:
                print(f"[存档管理器] 加载分类学数据失败: {e}")
                save_data["taxonomy"] = None
        else:
            save_data["taxonomy"] = None
        
        # ========== 加载事件 Embedding ==========
        event_embeddings_path = save_dir / "event_embeddings.json"
        if event_embeddings_path.exists():
            try:
                save_data["event_embeddings"] = json.loads(event_embeddings_path.read_text(encoding="utf-8"))
                print(f"[存档管理器] 已加载事件 embedding 数据")
            except Exception as e:
                print(f"[存档管理器] 加载事件 embedding 失败: {e}")
                save_data["event_embeddings"] = None
        else:
            save_data["event_embeddings"] = None
        
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
    
    def get_save_dir(self, save_name: str) -> Path | None:
        """获取存档目录路径（公开方法）"""
        return self._find_save_dir(save_name)
