# 后端重构指南

## 概述

本次重构解决了 `routes.py` (4700+ 行) 中的以下问题：

1. **服务实例化耦合**: 所有服务在模块导入时实例化，难以测试和替换
2. **全局状态分散**: `simulation_running`、`pressure_queue` 等状态散落在模块级变量
3. **配置读取重复**: 各模块分别调用 `_load_*_config`，存在 I/O 冗余
4. **职责混杂**: 模拟控制、物种管理、神性系统等多条业务线耦合在一起

## 快速启动

```bash
# 使用新架构（默认）
uvicorn backend.app.main:app --reload

# 使用旧版 routes.py（过渡期）
USE_LEGACY_ROUTES=true uvicorn backend.app.main:app --reload
```

## 新架构

### 目录结构

```
backend/app/
├── core/
│   ├── container.py      # 服务容器 (依赖注入)
│   ├── config_service.py # 配置统一管理
│   ├── session.py        # 会话状态管理
│   ├── config.py         # 静态配置
│   └── database.py       # 数据库
├── api/
│   ├── dependencies.py   # FastAPI Depends
│   ├── simulation.py     # 回合/存档路由
│   ├── species.py        # 物种管理路由
│   ├── divine.py         # 能量/成就路由
│   ├── ecosystem.py      # 食物网/健康路由
│   ├── analytics.py      # 导出/诊断路由
│   ├── router.py         # 路由聚合器
│   └── routes.py         # [旧] 仅在 USE_LEGACY_ROUTES=true 时使用
└── ...
```

### 核心组件

#### 1. ServiceContainer (`core/container.py`)

统一管理所有服务实例的创建和生命周期：

```python
from backend.app.core.container import get_container

container = get_container()
species_repo = container.species_repository
simulation_engine = container.simulation_engine
```

**特性**:
- `cached_property` 实现延迟初始化
- `override()` 方法支持测试替身
- 消除导入时的副作用

**容器管理的服务**:
- 仓储: `species_repository`, `environment_repository`, `history_repository`, `genus_repository`
- 服务: `embedding_service`, `model_router`, `save_manager`, `species_generator`
- 分析: `report_builder`, `export_service`, `niche_analyzer`, `focus_processor`, `critical_analyzer`
- 地图: `map_manager`, `map_evolution`, `migration_advisor`
- 物种: `speciation_service`, `reproduction_service`, `hybridization_service`, `gene_flow_service`
- 模拟: `environment_system`, `mortality_engine`, `simulation_engine`

#### 2. ConfigService (`core/config_service.py`)

统一配置读取，消除分散的 `_load_*_config`：

```python
from backend.app.core.container import get_container

config_service = get_container().config_service

# 获取各类配置（带缓存）
ecology = config_service.get_ecology_balance()
mortality = config_service.get_mortality()
speciation = config_service.get_speciation()
reproduction = config_service.get_reproduction()
predation = config_service.get_predation()
```

**特性**:
- 带缓存的配置读取（检测文件修改时间）
- `invalidate_cache()` 支持配置热加载
- 线程安全

#### 3. SimulationSessionManager (`core/session.py`)

集中管理运行时状态：

```python
from backend.app.core.session import get_session_manager

session = get_session_manager()

# 状态检查（只读接口）
can_start, reason = session.can_start_simulation()
queue_status = session.get_queue_status()

# 事件推送
session.push_event("complete", "推演完成", "系统")

# 使用锁确保互斥
with session.simulation_lock():
    # 执行模拟...
```

**管理的状态**:
- `is_running`: 模拟运行状态
- `current_save_name`: 当前存档
- `pressure_queue`: 压力队列（返回副本，不直接暴露对象）
- `events`: SSE 事件队列

**只读查询接口**:
- `get_queue_status()`: 获取队列状态
- `get_events_count()`: 获取待处理事件数量
- `can_start_simulation()`: 检查是否可开始模拟
- `can_modify_save()`: 检查是否可修改存档

#### 4. FastAPI 依赖注入 (`api/dependencies.py`)

```python
from fastapi import Depends
from .dependencies import (
    get_container,
    get_session,
    get_species_repository,
    require_not_running,
    require_save_loaded,
)

@router.get("/species")
def list_species(
    repo = Depends(get_species_repository),
):
    return repo.list_species()

@router.post("/saves/load")
def load_save(
    _: None = Depends(require_not_running),  # 检查模拟未运行
    save_name: str = Depends(require_save_loaded),  # 检查已加载存档
):
    ...
```

**可用依赖**:
- `get_container()`: 获取服务容器
- `get_session()`: 获取会话管理器
- `get_config()`: 获取配置服务
- `get_species_repository()`, `get_environment_repository()`, etc.
- `require_not_running`: 要求模拟未运行
- `require_save_loaded`: 要求已加载存档

## 路由拆分

| 模块 | 端点数 | 职责 | 主要端点 |
|------|--------|------|----------|
| `simulation.py` | 11 | 回合推演、存档管理 | `/turns/run`, `/saves/*`, `/queue/*` |
| `species.py` | 17 | 物种增删改查、干预 | `/species/*`, `/intervention/*`, `/lineage` |
| `divine.py` | 34 | 能量、成就、杂交、神力进阶 | `/energy/*`, `/achievements/*`, `/divine/*` |
| `ecosystem.py` | 9 | 食物网、生态健康 | `/ecosystem/*` |
| `analytics.py` | 14 | 导出、诊断、配置 | `/exports`, `/system/*`, `/config/*` |
| **合计** | **85** | 与 routes.py 完全匹配 | |

## 配置迁移

### 旧代码（不推荐）

```python
# simulation/species.py - 直接读取文件
def _load_ecology_balance_config():
    ui_config = environment_repository.load_ui_config(path)
    return ui_config.ecology_balance
```

### 新代码（推荐）

```python
# 优先使用 ConfigService
from backend.app.core.container import get_container

config = get_container().config_service
ecology = config.get_ecology_balance()
mortality = config.get_mortality()
```

### 渐进迁移模式

`resource_manager.py` 等模块已更新为优先使用 ConfigService，并在容器未初始化时回退到直接读取：

```python
def _load_resource_config():
    try:
        # 优先使用 ConfigService
        from ...core.container import get_container
        container = get_container()
        if hasattr(container, 'config_service'):
            return container.config_service.get_ui_config().resource_system
    except Exception:
        pass  # 容器未初始化时回退
    
    # 回退：直接读取文件
    # ...
```

## 中间件改进

`RequestLoggingMiddleware` 已更新为使用结构化日志：

```python
# 旧：print 输出
print(f"[{level}] {status_code} | {method} | {path}")

# 新：结构化日志
log_extra = {
    "method": method,
    "path": path,
    "status": status_code,
    "duration_ms": round(duration_ms, 1),
    "client": client_host,
    "session": session_id,
}
logger.debug(f"HTTP {status_code} {method} {path}", extra=log_extra)
```

## 测试支持

### 服务替身

```python
from backend.app.core.container import get_container, reset_container

def test_with_mock():
    container = get_container()
    
    # 注入 mock
    mock_repo = MockSpeciesRepository()
    container.override("species_repository", mock_repo)
    
    # 运行测试...
    
    # 清理
    reset_container()
```

### 会话状态隔离

```python
from backend.app.core.session import get_session_manager, reset_session_manager

def test_session():
    session = get_session_manager()
    session.reset_for_new_game()
    
    # 测试逻辑...
    
    reset_session_manager()
```

## 后续优化建议

1. **TileBasedMortalityEngine 拆分**:
   - 环境压力策略
   - 竞争计算策略
   - 捕食计算策略
   - AI 调整策略

2. **ResourceManager 集成**:
   - 在 Pipeline Stage 中注入 ResourceManager
   - 统一 NPP/承载计算
   - 为 TileBasedMortalityEngine 预留资源输入口

3. **Stage 注册表**:
   - 在 `simulation/pipeline` 中实现插件注册
   - 支持动态加载 Stage
   - 便于 A/B 测试不同算法

4. **结构化日志**:
   - 为每个 Stage 定义统一的结果对象
   - 引入 turn/stage/species_id 结构化字段

5. **测试覆盖**:
   - API 集成测试（mock AI/Embedding）
   - ResourceManager 单测
   - SessionManager 单测
   - Container override 行为测试

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `USE_LEGACY_ROUTES` | `false` | 是否使用旧版 routes.py |
| `LOG_LEVEL` | `INFO` | 日志级别 |
