# 板块构造演化系统

一个独立的板块构造模拟模块，用于模拟地质时间尺度的地形演化。

## 模块结构

```
tectonic/
├── __init__.py           # 模块入口和导出
├── config.py             # 配置常量
├── models.py             # 数据模型
├── plate_generator.py    # 板块生成器
├── motion_engine.py      # 板块运动引擎
├── geological_features.py # 地质特征分布器
├── matrix_engine.py      # 矩阵计算引擎
├── species_tracker.py    # 物种-板块追踪器
├── tectonic_system.py    # 主系统类
├── README.md             # 本文档
└── tests/                # 测试目录
    ├── __init__.py
    ├── run_tests.py
    ├── test_plate_generator.py
    ├── test_motion_engine.py
    ├── test_geological_features.py
    └── test_tectonic_system.py
```

## 快速开始

### 基本使用

```python
from backend.app.services.tectonic import TectonicSystem

# 初始化系统
system = TectonicSystem(width=128, height=40, seed=12345)

# 执行一个回合
result = system.step(pressure_modifiers={"volcanic_eruption": 5})

# 查看结果
print(f"回合 {result.turn_index}")
print(f"地形变化: {len(result.terrain_changes)} 处")
print(f"地质事件: {len(result.events)} 个")
print(f"火山喷发: {result.volcanoes_erupted} 次")
print(f"地震发生: {result.earthquakes_occurred} 次")

# 获取板块信息
plates = system.get_plates()
for plate in plates:
    print(f"板块 {plate.id}: {plate.plate_type.value}, 速度 {plate.speed():.3f}")

# 获取火山信息
volcanoes = system.get_volcanoes()
for v in volcanoes:
    print(f"火山 {v.name} 在 ({v.x}, {v.y}), 强度 {v.intensity:.2f}")
```

### 带物种追踪

```python
from backend.app.services.tectonic import TectonicSystem
from backend.app.services.tectonic.species_tracker import SimpleSpecies, SimpleHabitat

# 初始化
system = TectonicSystem(width=128, height=40, seed=42)

# 创建物种和栖息地
species = [
    SimpleSpecies(id=1, lineage_code="SP001", name="物种A"),
    SimpleSpecies(id=2, lineage_code="SP002", name="物种B"),
]

habitats = [
    SimpleHabitat(tile_id=100, species_id=1, population=1000),
    SimpleHabitat(tile_id=200, species_id=2, population=500),
]

# 执行并追踪物种
result = system.step(species_list=species, habitats=habitats)

# 检查物种隔离事件
for event in result.isolation_events:
    print(f"物种 {event.species_id} 被隔离在板块 {event.plate_a} 和 {event.plate_b} 之间")

# 检查物种接触事件
for event in result.contact_events:
    print(f"物种 {event.species_a_id} 和 {event.species_b_id} 在板块碰撞后接触")
```

### 手动触发火山喷发

```python
# 触发火山喷发（响应玩家压力）
events = system.trigger_volcanic_eruption(
    pressure_type="supervolcano",
    intensity=9,
    target_region=(64, 20),  # 可选：指定区域
    radius=10                 # 搜索半径
)

for event in events:
    print(f"{event.description}, 影响半径 {event.affected_radius}")
```

### 保存和加载

```python
# 保存状态
system.save("data/tectonic_state.json")

# 加载状态
system2 = TectonicSystem.load("data/tectonic_state.json")
```

## 核心概念

### 板块类型

| 类型 | 说明 | 密度 |
|------|------|------|
| continental | 大陆板块 | 2.7 g/cm³ |
| oceanic | 洋壳板块 | 3.0 g/cm³ |
| mixed | 混合板块 | 2.85 g/cm³ |

### 边界类型

| 类型 | 说明 | 地质效应 |
|------|------|----------|
| divergent | 张裂边界 | 洋中脊、裂谷、下沉 |
| convergent | 碰撞边界 | 造山、隆起 |
| subduction | 俯冲边界 | 海沟、火山弧 |
| transform | 转换边界 | 地震 |

### 压力影响

系统支持以下压力类型的影响：

| 压力类型 | 效果 |
|----------|------|
| orogeny | 增加碰撞速度、加速造山 |
| volcanic_eruption | 增加火山喷发概率 |
| earthquake_period | 增加全局速度、地震概率 |
| rifting | 增加张裂速度 |
| glacial_period | 降低全局速度 |

## 配置

所有配置在 `config.py` 中定义，主要包括：

- 板块生成参数（数量、大小分布、边界噪声）
- 运动参数（速度、衰减、极地效应）
- 地形变化参数（隆起/下沉速率）
- 地质特征参数（火山分布、热点）
- 事件概率参数

## 运行测试

```bash
cd backend

# 快速验证测试
python -m app.services.tectonic.tests.run_tests --quick

# 完整pytest测试
python -m pytest app/services/tectonic/tests/ -v
```

## 接入主系统

当准备好接入主演化系统时，需要：

1. 在 `SimulationEngine` 中初始化 `TectonicSystem`
2. 在每回合调用 `tectonic_system.step(pressure_modifiers)`
3. 将 `result.terrain_changes` 应用到主系统的 `MapTile`
4. 将 `result.events` 添加到回合报告
5. 将 `result.pressure_feedback` 合并到压力系统
6. 将 `result.isolation_events` 和 `result.contact_events` 传递给物种系统

示例集成代码：

```python
# 在 SimulationEngine.__init__ 中
self.tectonic = TectonicSystem(
    width=map_manager.width,
    height=map_manager.height,
    seed=config.seed
)

# 在 run_turns_async 中
tectonic_result = self.tectonic.step(
    pressure_modifiers=parsed_pressures,
    species_list=current_species,
    habitats=current_habitats,
)

# 应用地形变化
for change in tectonic_result.terrain_changes:
    tile = map_manager.get_tile(change.tile_id)
    tile.elevation = change.new_elevation

# 合并压力反馈
for key, value in tectonic_result.pressure_feedback.items():
    environment_modifiers[key] = environment_modifiers.get(key, 0) + value
```




