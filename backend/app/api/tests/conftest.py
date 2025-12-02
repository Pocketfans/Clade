"""
API 测试夹具

提供用于 API 测试的共享夹具和模拟对象。
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_container():
    """创建模拟服务容器"""
    container = MagicMock()
    
    # ConfigService
    container.config_service = MagicMock()
    container.config_service.get_ui_config = MagicMock(return_value=MagicMock(
        food_web=MagicMock(),
        ecology_balance=MagicMock(),
        mortality=MagicMock(),
        speciation=MagicMock(),
        resource_system=MagicMock(),
    ))
    container.config_service.get_ecology_balance = MagicMock(return_value=MagicMock())
    container.config_service.get_mortality = MagicMock(return_value=MagicMock())
    container.config_service.get_speciation = MagicMock(return_value=MagicMock())
    
    # ResourceManager
    container.resource_manager = MagicMock()
    container.resource_manager.get_snapshot = MagicMock(return_value=MagicMock(
        total_npp=1000.0,
        avg_npp=100.0,
        overgrazing_tiles=0,
    ))
    
    # Repositories
    container.species_repository = MagicMock()
    container.species_repository.list_species = MagicMock(return_value=[])
    container.species_repository.get_by_lineage = MagicMock(return_value=None)
    
    container.environment_repository = MagicMock()
    container.history_repository = MagicMock()
    container.history_repository.list_turns = MagicMock(return_value=[])
    
    container.genus_repository = MagicMock()
    
    # Services
    container.save_manager = MagicMock()
    container.save_manager.list_saves = MagicMock(return_value=[])
    
    container.export_service = MagicMock()
    container.model_router = MagicMock()
    container.embedding_service = MagicMock()
    container.species_generator = MagicMock()
    
    # SimulationEngine
    container.simulation_engine = MagicMock()
    container.simulation_engine.turn_counter = 0
    
    # EnvironmentSystem
    container.environment_system = MagicMock()
    
    return container


@pytest.fixture
def mock_session():
    """创建模拟会话管理器"""
    session = MagicMock()
    session.session_id = "test-session-12345678"
    session.is_running = False
    session.current_save_name = None
    session.autosave_counter = 0
    session.pressure_queue = []
    session.get_pending_events = MagicMock(return_value=[])
    session.push_event = MagicMock()
    session.set_running = MagicMock()
    session.pop_pressure = MagicMock(return_value=None)
    return session



