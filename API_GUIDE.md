# API 接口指南

本文档是前后端交互的契约。前端开发者应参考此文档进行 API 调用，后端开发者应以此为标准实现接口。

> **注意**：所有 API 的基础路径 (Base URL) 均为 `/api`。

## 1. 模拟控制 (Simulation)

负责推进游戏时间、管理压力队列。

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `POST` | `/turns/run` | **核心接口**：执行 N 个回合 | `rounds`: int, `pressures`: List[Pressure] |
| `GET` | `/queue` | 获取当前压力队列状态 | - |
| `POST` | `/queue/add` | 向队列添加未来压力 | `pressures`: List[Pressure], `rounds`: int |
| `POST` | `/queue/clear` | 清空压力队列 | - |
| `GET` | `/history` | 获取历史回合报告 | `limit`: int |
| `GET` | `/exports` | 获取导出的历史记录文件 | - |
| `GET` | `/pressures/templates` | 获取可用压力模板列表 | - |

## 2. 物种情报 (Species)

查询物种详情、谱系关系与统计数据。

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/species/list` | 获取所有物种简表 | - |
| `GET` | `/species/{code}` | 获取特定物种详情 | `code`: lineage_code (e.g., "A1") <br> **注**：响应包含 `organs`, `capabilities`, `trophic_level` 等详细信息 |
| `POST` | `/species/generate` | **AI 生成**：基于 Prompt 生成新物种 | `prompt`: str, `lineage_code`: str |
| `POST` | `/species/edit` | 手动干预/编辑物种 | `trait_overrides`: dict, `open_new_lineage`: bool |
| `GET` | `/lineage` | 获取完整族谱树数据 | - |
| `GET` | `/species/{c1}/can_hybridize/{c2}` | **杂交检查** | - |
| `GET` | `/genus/{code}/relationships` | 查询属内遗传关系 | - |

## 3. 地图与环境 (Environment)

获取六边形网格数据与配置。

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/map` | 获取地图切片与概览 | `view_mode`: "terrain"\|"bio", `limit_tiles`: int |
| `GET` | `/config/ui` | 获取 UI 配置 | - |
| `POST` | `/config/ui` | 更新 UI 配置 | `config`: UIConfig |

## 4. 分析与 AI (Analytics)

调用后端的高级分析能力。

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `POST` | `/niche/compare` | **生态位对比** | `species_a`, `species_b` |
| `GET` | `/watchlist` | 获取当前关注物种列表 | - |
| `POST` | `/watchlist` | 更新关注物种列表 | `lineage_codes`: List[str] |
| `POST` | `/config/test-api` | 测试 LLM 连接 | `type`, `base_url`, `api_key`, `model` |

## 5. 存档管理 (Saves)

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/saves/list` | 列出所有存档 | - |
| `POST` | `/saves/create` | 创建新存档 | `save_name`, `scenario`, `species_prompts` |
| `POST` | `/saves/save` | 保存当前进度 | `save_name` |
| `POST` | `/saves/load` | 加载存档 | `save_name` |
| `DELETE` | `/saves/{save_name}` | 删除存档 | - |

## 6. 管理与运维 (Admin)

| 方法 | 路径 | 描述 | 关键参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/admin/health` | 系统健康检查 | - |
| `POST` | `/admin/reset` | 重置世界状态 | `keep_saves`: bool, `keep_map`: bool |
| `POST` | `/admin/simulate-terrain` | 地形演化沙盒模拟 | `turns`: int, `width`: int, `height`: int |

## 7. 前端集成指引

### 7.1 调用方式
前端所有 API 调用封装在 `frontend/src/services/api.ts` 中。请勿在组件中直接使用 `fetch`。

```typescript
// 推荐写法
import { api } from '../services/api';
const data = await api.fetchSpeciesDetail('A1');
```

### 7.2 错误处理
后端统一返回 HTTP 状态码：
- `200 OK`: 成功。
- `404 Not Found`: 物种或存档不存在。
- `500 Internal Server Error`: 模拟计算出错（通常是 AI 服务超时或数据库锁）。

### 7.3 类型定义
所有请求/响应的 TypeScript 类型定义在 `frontend/src/services/api.types.ts`。后端修改 Pydantic 模型后，需同步更新此文件。

### 7.4 数据可视化支持
前端组件依赖特定的 API 数据结构：
- **GlobalTrendsPanel**: 依赖 `/history` 返回的 `TurnReport` 数组。
- **SpeciesLedger**: 依赖 `/species/list` 返回的 `SpeciesList`。
- **OrganismBlueprint**: 依赖 `/species/{code}` 返回的 `organs` 和 `morphology_stats`。
- **MapPanel**: 依赖 `/map` 返回的 `MapOverview`。
