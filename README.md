# EvoSandbox

EvoSandbox 是一款本地运行的 AI 物种演化沙盒。后端基于 FastAPI + SQLModel 管理地图、物种与推演流程，前端使用 React + Vite 提供策略 HUD。仓库同时包含运行所需的嵌入缓存、存档、导出目录等资源。

## 项目概览
- **回合驱动的模拟流水线**：`SimulationEngine` 串联环境、死亡、营养级互动、规则、AI 推理与导出服务，通过 REST API 对前端开放。
- **React HUD**：`MapPanel`、`ControlPanel`、HUD 浮窗与设置抽屉放在 `frontend/src/components`，配合 `MapViewSelector` 和 `MapLegend` 呈现 80×40 六边形世界。
- **模型与嵌入路由**：`app/ai/ModelRouter` 根据 `settings.json` 选择不同 provider/model，并由 `EmbeddingService` 负责缓存。
- **三层物种分析**：Critical（玩家关注，最多3个，逐个详细分析）、Focus（生态强度排序，默认24个，批量处理）、Background（低种群/低强度，规则计算）。分层基于营养级权重、种群规模、濒危程度多维度评分，顶级捕食者即使种群小也优先关注。
- **生态位对比**：`NicheCompareView` 通过向量化计算展示物种间的生态位重叠度、相似度与竞争强度，支持多维度对比。
- **物种属性与演化机制**：物种具备耐寒性/耐热性/耐旱性/耐盐性等环境适应属性（1.0-15.0标度），支持动态添加新属性（如耐高压/耐酸性），支持渐进演化与退化。`organs` 字段记录结构化器官（运动/感觉/代谢/防御等），`capabilities` 字段存储能力标签。
- **营养级与属性限制**：物种的营养级决定其在食物链中的位置和属性上限。生产者（T1.0）属性总和≤30，草食者（T2.0）≤50，中层捕食者（T3.0）≤80，高层捕食者（T4.0）≤105，顶级掠食者（T5.0+）≤135。引入克莱伯定律（Kleiber's Law）模拟大型生物的低单位代谢率。单属性最多达到特化上限，最多2个属性可超过基础上限。
- **基因库系统**：属（Genus）维护共享的基因库，记录AI发现的新特质和器官。物种携带休眠基因，在环境压力下可激活潜在特质。
- **分化与竞争**：分化遵循奠基者效应（Founder Effect），父代保留大部分（60-80%）种群，子代由边缘小群体建立。分化后3回合内亲代承受5-15%演化滞后debuff，同属子代对亲代施加最高25%竞争压力。
- **亚种与遗传距离**：新分化物种初始为亚种（taxonomic_rank=subspecies），15回合后晋升为独立种。
- **迁徙与扩散**：三种类型：压力驱动迁徙（死亡率>20%）、资源饱和扩散（资源压力>1.2）、人口溢出（增长>150%且资源压力>1.0）。
- **数据持久化**：SQLite (`egame.db`) 储存游戏状态，`reports/`、`exports/`、`saves/` 负责回合导出与独立存档。

## 目录结构

```
backend/              # 后端核心代码
  app/
    ai/               # 模型路由、Prompt 模板
    api/              # FastAPI 路由与 UI 配置
    core/             # 设置、数据库、默认种子
    models/           # SQLModel 定义
    repositories/     # 数据访问层
    services/         # 规则/工具服务
    simulation/       # SimulationEngine 及子系统
  pyproject.toml
frontend/             # 前端代码 (React + Vite)
scripts/              # 工具脚本
data/                 # 运行时数据 (已忽略)
  db/                 # SQLite 数据库
  saves/              # 存档
  exports/            # 导出数据
  reports/            # 回合报告
  logs/               # 日志
  cache/              # 嵌入缓存
  settings.json       # UI 配置
```

## 快速开始

### 后端

请在项目根目录下运行：

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate

# 安装依赖
pip install -e backend/[dev]
copy backend\.env.example .env        # macOS/Linux: cp backend/.env.example .env

# 启动服务 (从根目录运行)
uvicorn backend.app.main:app --reload --port 8000
```

首启会自动创建 `data/db/egame.db`、初始化 80×40 地图并导入 `backend/app/core/seed.py` 中的默认物种。

### 前端

```bash
cd frontend
npm install
npm run build
npm run dev
```

Vite 在 `http://localhost:5173` 提供界面，`vite.config.ts` 将 `/api` 代理到 `http://localhost:8000`。

## 关键数据与配置
- `.env`：位于根目录，配置数据库及 AI 接入所需的 Base URL/Key。
- `data/settings.json`：UI 设置抽屉持久化的主模型、能力覆盖与嵌入配置。
- `data/cache/embeddings/`：`EmbeddingService` 以 SHA256 命名缓存向量。
- `data/reports/`、`data/exports/`：`ExportService` 输出 Markdown/JSON 年鉴与世界快照。
- `data/saves/`：独立存档目录。
- `data/logs/`：运行日志。
- 物种关注列表通过 `GET/POST /api/watchlist` 管理，决定 Critical 层分配（默认最多3个）。
- 回合报告（`TurnReport`）包含地形变化类型（`MapChange.change_type`）、分化原因（`BranchingEvent.reason`）及物种 AI 分析（`SpeciesSnapshot.notes`）。
## 地形演化测试
- 运行 `python test_terrain_evolution.py` 会创建临时存档并执行 10 轮推演，`TerrainEvolutionService` 在缺省外部模型时会启用规则驱动的候选区推断并输出阶段、事件与最大海拔改变量。
- 日志需重点核对 5 个验证点：①板块阶段与事件类型是否匹配；②是否出现火山抬升并反映在海拔统计；③持续过程是否跨回合延续；④侵蚀/造山/火山幅度是否落在 5-30m、100-500m、200-800m 区间；⑤规则分析是否符合地质逻辑。
- 测试结束自动写入 `test_output.log`，便于提交前留档。
## 贡献指引

1. 变更 API 后同步更新 `frontend/src/services/api.ts` 与相关类型定义。
2. 运行 `uvicorn app.main:app`、`npm run dev`、`npm run build` 确认基础流程可用。
3. 不要误删用户数据目录（`egame.db`、`reports/`、`exports/`、`saves/`）。
4. PR 描述建议包含功能概述、影响面与风险提示。

## 许可

若仓库未附带 LICENSE，则默认专有，仅在作者授权范围内使用；如需授权请联系作者。
