from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ...models.species import Species

logger = logging.getLogger(__name__)
from ...models.environment import MapState, MapTile, HabitatPopulation
from ...models.history import TurnLog
from ...models.genus import Genus
from ...repositories.species_repository import species_repository
from ...repositories.environment_repository import environment_repository
from ...repositories.history_repository import history_repository
from ...repositories.genus_repository import genus_repository

if TYPE_CHECKING:
    from .embedding import EmbeddingService
    from .divine_energy import DivineEnergyService
    from .divine_progression import DivineProgressionService


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
        embedding_service: 'EmbeddingService | None' = None,
        energy_service: 'DivineEnergyService | None' = None,
        progression_service: 'DivineProgressionService | None' = None
    ) -> None:
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        self._embedding_service = embedding_service
        self._energy_service = energy_service
        self._progression_service = progression_service

    def set_embedding_service(self, service: 'EmbeddingService') -> None:
        """设置 embedding 服务（延迟注入）"""
        self._embedding_service = service

    def set_energy_service(self, service: 'DivineEnergyService') -> None:
        """设置能量服务（延迟注入）"""
        self._energy_service = service

    def set_progression_service(self, service: 'DivineProgressionService') -> None:
        """设置神力进阶服务（延迟注入）"""
        self._progression_service = service

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
                logger.info(f"[存档管理器] 读取存档元数据失败: {save_dir.name}, {e}")
                continue
        
        # 按最后保存时间排序
        saves.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
        return saves

    def create_save(self, save_name: str, scenario: str = "原初大陆") -> dict[str, Any]:
        """创建新存档"""
        logger.info(f"[存档管理器] 创建新存档: {save_name}")
        
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
        
        logger.info(f"[存档管理器] 存档创建成功: {save_dir.name}")
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
        
        【健壮性改进】
        - 校验 turn_index 与历史记录的一致性
        - 确保 metadata 和 game_state 的回合数同步
        """
        # 校验回合数有效性
        if turn_index < 0:
            logger.warning(f"[存档管理器] 回合数异常: {turn_index}，修正为 0")
            turn_index = 0
        
        logger.info(f"[存档管理器] 保存游戏: {save_name}, 回合={turn_index}")
        
        # 查找或创建存档目录
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            logger.info(f"[存档管理器] 存档不存在，创建新存档")
            self.create_save(save_name)
            save_dir = self._find_save_dir(save_name)
        
        # 获取所有数据
        species_list = species_repository.list_species()
        map_tiles = environment_repository.list_tiles()
        map_state = environment_repository.get_state()
        habitats = environment_repository.list_habitats()
        history_logs = history_repository.list_turns(limit=1000)
        genus_list = genus_repository.list_all()
        
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
            "genus_list": [g.model_dump(mode="json") for g in genus_list],
        }
        
        logger.info(f"[存档管理器] 保存数据: {len(species_list)} 物种, {len(map_tiles)} 地块, {len(habitats)} 栖息地, {len(history_logs)} 历史记录, {len(genus_list)} 属")
        
        (save_dir / "game_state.json").write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # ========== 保存 Embedding 数据 ==========
        if self._embedding_service and species_list:
            try:
                # 使用统一的描述文本构建方法，确保缓存key一致
                from .embedding import EmbeddingService
                descriptions = [
                    EmbeddingService.build_species_text(sp, include_traits=True, include_names=True)
                    for sp in species_list
                ]
                embedding_data = self._embedding_service.export_embeddings(descriptions)
                embedding_data["species_count"] = len(species_list)
                embedding_data["saved_at"] = datetime.now().isoformat()
                
                (save_dir / "embeddings.json").write_text(
                    json.dumps(embedding_data, ensure_ascii=False),
                    encoding="utf-8"
                )
                logger.info(f"[存档管理器] 已保存 {len(embedding_data.get('embeddings', {}))} 个 embedding 向量")
            except Exception as e:
                logger.info(f"[存档管理器] 保存 embedding 数据失败: {e}")
        
        # ========== 保存分类学数据 ==========
        if taxonomy_data:
            try:
                (save_dir / "taxonomy.json").write_text(
                    json.dumps(taxonomy_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"[存档管理器] 已保存分类学数据")
            except Exception as e:
                logger.info(f"[存档管理器] 保存分类学数据失败: {e}")
        
        # ========== 保存事件 Embedding ==========
        if event_embeddings:
            try:
                (save_dir / "event_embeddings.json").write_text(
                    json.dumps(event_embeddings, ensure_ascii=False),
                    encoding="utf-8"
                )
                logger.info(f"[存档管理器] 已保存事件 embedding 数据")
            except Exception as e:
                logger.info(f"[存档管理器] 保存事件 embedding 失败: {e}")
        
        # ========== 保存能量状态 ==========
        if self._energy_service:
            try:
                energy_data = {
                    "state": self._energy_service.get_state().to_dict(),
                    "enabled": self._energy_service.enabled,
                    "history": self._energy_service.get_history(limit=50),
                }
                (save_dir / "energy.json").write_text(
                    json.dumps(energy_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"[存档管理器] 已保存能量状态: {energy_data['state']['current']}/{energy_data['state']['maximum']}")
            except Exception as e:
                logger.info(f"[存档管理器] 保存能量状态失败: {e}")
        
        # ========== 保存神力进阶状态 ==========
        if self._progression_service:
            try:
                progression_data = self._progression_service.export_state()
                (save_dir / "divine_progression.json").write_text(
                    json.dumps(progression_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                path_info = self._progression_service.get_path_info()
                path_name = path_info["name"] if path_info else "未选择"
                logger.info(f"[存档管理器] 已保存神力进阶状态: 神格={path_name}")
            except Exception as e:
                logger.info(f"[存档管理器] 保存神力进阶状态失败: {e}")
        
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
        
        # 【优化】只在 DEBUG 模式下验证一致性，避免阻塞 I/O
        # 正常保存流程已确保数据一致，无需重复读取大文件
        if logger.isEnabledFor(logging.DEBUG):
            self._verify_save_integrity(save_dir, turn_index, len(species_list))
        
        logger.info(f"[存档管理器] 游戏保存成功: {save_dir.name}")
        return save_dir
    
    def _verify_save_integrity(
        self, 
        save_dir: Path, 
        expected_turn: int, 
        expected_species_count: int
    ) -> bool:
        """验证存档完整性（轻量级检查）
        
        【优化】只验证 metadata.json，不读取大文件 game_state.json
        完整验证应在加载时通过 _validate_and_fix_turn_index 进行
        
        Returns:
            bool: 验证是否通过
        """
        issues: list[str] = []
        
        # 检查必需文件是否存在（不读取内容）
        required_files = ["metadata.json", "game_state.json"]
        for fname in required_files:
            if not (save_dir / fname).exists():
                issues.append(f"缺少必需文件: {fname}")
        
        if issues:
            for issue in issues:
                logger.error(f"[存档验证] {issue}")
            return False
        
        try:
            # 【优化】只验证 metadata（文件小）
            metadata = json.loads((save_dir / "metadata.json").read_text(encoding="utf-8"))
            meta_turn = metadata.get("turn_index")
            
            # 检查 metadata 回合数
            if meta_turn != expected_turn:
                issues.append(f"metadata 回合数不匹配: 预期={expected_turn}, 实际={meta_turn}")
                self._fix_save_inconsistency(save_dir, expected_turn)
            
            if issues:
                for issue in issues:
                    logger.warning(f"[存档验证] {issue}")
                return False
            
            logger.debug(f"[存档验证] 验证通过: 回合={expected_turn}")
            return True
            
        except Exception as e:
            logger.error(f"[存档验证] 验证过程出错: {e}")
            return False
    
    def _fix_save_inconsistency(self, save_dir: Path, correct_turn: int) -> None:
        """修复存档不一致问题
        
        【优化】只修复 metadata.json（文件小，I/O 快）
        game_state.json 在加载时会通过 _validate_and_fix_turn_index 校验
        避免读写可能很大的 game_state.json 文件（100MB+）
        """
        try:
            # 只修复 metadata（文件很小）
            metadata_path = save_dir / "metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("turn_index") != correct_turn:
                    metadata["turn_index"] = correct_turn
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    logger.info(f"[存档修复] 已修正 metadata 回合数为 {correct_turn}")
            
            # 【优化】不再修复 game_state.json
            # 原因：game_state 文件可能非常大（100MB+），读写会阻塞 I/O
            # 加载时 _validate_and_fix_turn_index 会从多来源校验回合数
                    
        except Exception as e:
            logger.error(f"[存档修复] 修复失败: {e}")

    def load_game(self, save_name: str) -> dict[str, Any]:
        """加载游戏存档
        
        Returns:
            包含以下键的字典:
            - turn_index, species, map_tiles, habitats, map_state, history_logs
            - embeddings_loaded: bool - 是否成功加载了 embedding
            - taxonomy: dict | None - 分类学数据
            - event_embeddings: dict | None - 事件 embedding 数据
        
        【健壮性改进】
        - 校验并修复 metadata 和 game_state 的回合数一致性
        - 支持从历史记录推断正确的回合数
        """
        logger.info(f"[存档管理器] 加载游戏: {save_name}")
        
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            raise FileNotFoundError(f"存档不存在: {save_name}")
        
        game_state_path = save_dir / "game_state.json"
        metadata_path = save_dir / "metadata.json"
        
        if not game_state_path.exists():
            raise FileNotFoundError(f"存档数据文件不存在: {save_name}")
        
        # 读取存档数据
        save_data = json.loads(game_state_path.read_text(encoding="utf-8"))
        
        # 【关键】校验并修复回合数一致性
        turn_index = self._validate_and_fix_turn_index(save_dir, save_data)
        save_data["turn_index"] = turn_index
        
        logger.info(f"[存档管理器] 加载数据: {len(save_data.get('species', []))} 物种, {len(save_data.get('map_tiles', []))} 地块, 回合={turn_index}")
        
        # 1. 清除当前运行时数据
        logger.info("[存档管理器] 清除当前运行时状态...")
        environment_repository.clear_state()
        species_repository.clear_state()
        history_repository.clear_state()
        genus_repository.clear_state()

        # 恢复物种数据到数据库
        restored_species = []
        for species_data in save_data.get("species", []):
            normalized = self._normalize_species_payload(species_data)
            species = Species(**normalized)
            species_repository.upsert(species)
            restored_species.append(species)
        
        # 恢复地图地块
        if save_data.get("map_tiles"):
            logger.info(f"[存档管理器] 恢复 {len(save_data['map_tiles'])} 个地块...")
            tiles = [MapTile(**tile_data) for tile_data in save_data["map_tiles"]]
            environment_repository.upsert_tiles(tiles)
        
        # 恢复地图状态
        if save_data.get("map_state"):
            map_state = MapState(**save_data["map_state"])
            environment_repository.save_state(map_state)

        # 恢复栖息地分布
        if save_data.get("habitats"):
            logger.info(f"[存档管理器] 恢复 {len(save_data['habitats'])} 个栖息地记录...")
            habitats = [HabitatPopulation(**h_data) for h_data in save_data["habitats"]]
            environment_repository.write_habitats(habitats)

        # 恢复历史记录
        if save_data.get("history_logs"):
            logger.info(f"[存档管理器] 恢复 {len(save_data['history_logs'])} 条历史记录...")
            for log_data in save_data["history_logs"]:
                if isinstance(log_data.get("created_at"), str):
                     try:
                        log_data["created_at"] = datetime.fromisoformat(log_data["created_at"].replace("Z", "+00:00"))
                     except ValueError:
                        pass
                log = TurnLog(**log_data)
                history_repository.log_turn(log)
        
        # 恢复属数据（Genus）
        if save_data.get("genus_list"):
            logger.info(f"[存档管理器] 恢复 {len(save_data['genus_list'])} 个属...")
            for genus_data in save_data["genus_list"]:
                genus = Genus(**genus_data)
                genus_repository.upsert(genus)
        
        # ========== 恢复 Embedding 数据 ==========
        embeddings_loaded = False
        embeddings_path = save_dir / "embeddings.json"
        if embeddings_path.exists() and self._embedding_service:
            try:
                embedding_data = json.loads(embeddings_path.read_text(encoding="utf-8"))
                # 使用统一的描述文本构建方法，确保缓存key一致
                from .embedding import EmbeddingService
                descriptions = [
                    EmbeddingService.build_species_text(sp, include_traits=True, include_names=True)
                    for sp in restored_species
                ]
                imported = self._embedding_service.import_embeddings(embedding_data, descriptions)
                embeddings_loaded = imported > 0
                logger.info(f"[存档管理器] 已恢复 {imported} 个 embedding 向量")
            except Exception as e:
                logger.info(f"[存档管理器] 恢复 embedding 数据失败: {e}")
        
        save_data["embeddings_loaded"] = embeddings_loaded
        
        # ========== 加载分类学数据 ==========
        taxonomy_path = save_dir / "taxonomy.json"
        if taxonomy_path.exists():
            try:
                save_data["taxonomy"] = json.loads(taxonomy_path.read_text(encoding="utf-8"))
                logger.info(f"[存档管理器] 已加载分类学数据")
            except Exception as e:
                logger.info(f"[存档管理器] 加载分类学数据失败: {e}")
                save_data["taxonomy"] = None
        else:
            save_data["taxonomy"] = None
        
        # ========== 加载事件 Embedding ==========
        event_embeddings_path = save_dir / "event_embeddings.json"
        if event_embeddings_path.exists():
            try:
                save_data["event_embeddings"] = json.loads(event_embeddings_path.read_text(encoding="utf-8"))
                logger.info(f"[存档管理器] 已加载事件 embedding 数据")
            except Exception as e:
                logger.info(f"[存档管理器] 加载事件 embedding 失败: {e}")
                save_data["event_embeddings"] = None
        else:
            save_data["event_embeddings"] = None
        
        # ========== 恢复能量状态 ==========
        energy_loaded = False
        energy_path = save_dir / "energy.json"
        if energy_path.exists() and self._energy_service:
            try:
                energy_data = json.loads(energy_path.read_text(encoding="utf-8"))
                
                # 恢复能量状态
                state = energy_data.get("state", {})
                self._energy_service.set_energy(
                    current=state.get("current", 100),
                    maximum=state.get("maximum", 100),
                    regen=state.get("regen_per_turn", 15),
                )
                
                # 恢复启用状态
                self._energy_service.enabled = energy_data.get("enabled", True)
                
                # 恢复历史统计（total_spent, total_regenerated）
                energy_state = self._energy_service.get_state()
                energy_state.total_spent = state.get("total_spent", 0)
                energy_state.total_regenerated = state.get("total_regenerated", 0)
                
                # 恢复历史记录
                self._energy_service._history.clear()
                for h in energy_data.get("history", []):
                    from .divine_energy import EnergyTransaction
                    self._energy_service._history.append(EnergyTransaction(
                        action=h.get("action", ""),
                        cost=h.get("cost", 0),
                        turn=h.get("turn", 0),
                        details=h.get("details", ""),
                        success=h.get("success", True),
                    ))
                
                energy_loaded = True
                logger.info(f"[存档管理器] 已恢复能量状态: {state.get('current', 100)}/{state.get('maximum', 100)}")
            except Exception as e:
                logger.info(f"[存档管理器] 恢复能量状态失败: {e}")
        elif self._energy_service:
            # 存档中没有能量数据，重置为默认状态
            self._energy_service.reset()
            logger.info(f"[存档管理器] 存档中无能量数据，已重置为默认状态")
        
        save_data["energy_loaded"] = energy_loaded
        
        # ========== 恢复神力进阶状态 ==========
        progression_loaded = False
        progression_path = save_dir / "divine_progression.json"
        if progression_path.exists() and self._progression_service:
            try:
                progression_data = json.loads(progression_path.read_text(encoding="utf-8"))
                self._progression_service.load_state(progression_data)
                progression_loaded = True
                path_info = self._progression_service.get_path_info()
                path_name = path_info["name"] if path_info else "未选择"
                logger.info(f"[存档管理器] 已恢复神力进阶状态: 神格={path_name}")
            except Exception as e:
                logger.info(f"[存档管理器] 恢复神力进阶状态失败: {e}")
        elif self._progression_service:
            # 存档中没有神力进阶数据，重置为默认状态
            self._progression_service.reset()
            logger.info(f"[存档管理器] 存档中无神力进阶数据，已重置为默认状态")
        
        save_data["progression_loaded"] = progression_loaded
        
        # 设置成功标志
        save_data["success"] = True
        save_data["species_count"] = len(restored_species)
        
        logger.info(f"[存档管理器] 游戏加载成功: {save_name}")
        return save_data

    def delete_save(self, save_name: str) -> bool:
        """删除存档"""
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            return False
        
        shutil.rmtree(save_dir)
        logger.info(f"[存档管理器] 存档已删除: {save_name}")
        return True

    def _validate_and_fix_turn_index(
        self, 
        save_dir: Path, 
        save_data: dict[str, Any]
    ) -> int:
        """校验并修复回合数一致性
        
        【健壮性检查】
        从多个来源获取回合数并选择最可靠的值：
        1. game_state.json 中的 turn_index
        2. metadata.json 中的 turn_index  
        3. map_state 中的 turn_index
        4. history_logs 中推断的最大回合数
        
        返回最可靠的回合数，并在检测到不一致时记录警告。
        """
        metadata_path = save_dir / "metadata.json"
        
        # 收集所有来源的回合数
        sources: dict[str, int] = {}
        
        # 1. game_state.json 中的 turn_index
        game_state_turn = save_data.get("turn_index")
        if game_state_turn is not None:
            sources["game_state"] = int(game_state_turn)
        
        # 2. metadata.json 中的 turn_index
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                meta_turn = metadata.get("turn_index")
                if meta_turn is not None:
                    sources["metadata"] = int(meta_turn)
            except Exception as e:
                logger.warning(f"[存档管理器] 读取 metadata 失败: {e}")
        
        # 3. map_state 中的 turn_index
        map_state = save_data.get("map_state")
        if map_state and "turn_index" in map_state:
            sources["map_state"] = int(map_state["turn_index"])
        
        # 4. 从 history_logs 推断（最大的 turn_index）
        history_logs = save_data.get("history_logs", [])
        if history_logs:
            max_history_turn = max(
                (log.get("turn_index", 0) for log in history_logs),
                default=0
            )
            # history 记录的是完成的回合，所以下一回合是 max + 1
            # 但如果存档是在回合结束后保存的，turn_counter 已经是 max + 1
            sources["history_inferred"] = max_history_turn + 1
        
        # 如果没有任何来源，返回 0
        if not sources:
            logger.warning(f"[存档管理器] 无法确定回合数，使用默认值 0")
            return 0
        
        # 检查一致性
        unique_values = set(sources.values())
        if len(unique_values) == 1:
            # 所有来源一致
            return list(unique_values)[0]
        
        # 存在不一致，记录详细信息
        logger.warning(f"[存档管理器] 检测到回合数不一致: {sources}")
        
        # 选择策略：优先使用 game_state，其次是 history_inferred
        # 因为 game_state 是最直接保存的值，history 可以验证
        if "game_state" in sources and "history_inferred" in sources:
            gs_turn = sources["game_state"]
            hist_turn = sources["history_inferred"]
            
            # 如果 game_state 与 history 推断相差太大，可能有问题
            if abs(gs_turn - hist_turn) <= 1:
                # 相差不超过1，使用较大的值
                chosen = max(gs_turn, hist_turn)
                logger.info(f"[存档管理器] 选择回合数: {chosen} (game_state={gs_turn}, history={hist_turn})")
                return chosen
            else:
                # 相差太大，优先信任 history（因为它是实际发生的记录）
                logger.warning(
                    f"[存档管理器] 回合数差异过大，使用历史推断值: {hist_turn}"
                )
                return hist_turn
        
        # 回退：使用所有来源中的最大值
        chosen = max(sources.values())
        logger.info(f"[存档管理器] 使用最大回合数: {chosen}")
        return chosen

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
    
    def check_save_integrity(self, save_name: str) -> dict[str, Any]:
        """检查存档完整性（公开方法）
        
        用于在UI中显示存档健康状态。
        
        Returns:
            包含以下键的字典:
            - valid: bool - 存档是否有效
            - issues: list[str] - 发现的问题列表
            - turn_index: int | None - 检测到的回合数
            - fixed: bool - 是否自动修复了问题
        """
        result = {
            "valid": True,
            "issues": [],
            "turn_index": None,
            "fixed": False,
        }
        
        save_dir = self._find_save_dir(save_name)
        if not save_dir:
            result["valid"] = False
            result["issues"].append("存档目录不存在")
            return result
        
        # 检查必需文件
        required_files = ["metadata.json", "game_state.json"]
        for fname in required_files:
            if not (save_dir / fname).exists():
                result["valid"] = False
                result["issues"].append(f"缺少必需文件: {fname}")
        
        if not result["valid"]:
            return result
        
        try:
            # 读取并验证数据
            metadata = json.loads((save_dir / "metadata.json").read_text(encoding="utf-8"))
            game_state = json.loads((save_dir / "game_state.json").read_text(encoding="utf-8"))
            
            meta_turn = metadata.get("turn_index")
            gs_turn = game_state.get("turn_index")
            
            # 使用校验方法获取正确的回合数
            correct_turn = self._validate_and_fix_turn_index(save_dir, game_state)
            result["turn_index"] = correct_turn
            
            # 检查不一致
            if meta_turn != gs_turn:
                result["issues"].append(f"回合数不一致: metadata={meta_turn}, game_state={gs_turn}")
                result["valid"] = False
                
                # 尝试自动修复
                self._fix_save_inconsistency(save_dir, correct_turn)
                result["fixed"] = True
                result["valid"] = True  # 修复后认为有效
            
            # 检查 map_state 一致性
            map_state = game_state.get("map_state")
            if map_state and map_state.get("turn_index") != correct_turn:
                result["issues"].append(
                    f"map_state 回合数不一致: {map_state.get('turn_index')} vs {correct_turn}"
                )
            
        except Exception as e:
            result["valid"] = False
            result["issues"].append(f"读取存档数据失败: {e}")
        
        return result
