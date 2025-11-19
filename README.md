# EvoSandbox: 规则约束下的 AI 演化沙盒

**EvoSandbox** 是一个基于混合架构（Hybrid Architecture）的生物演化模拟系统。它旨在解决纯 AI 模拟中常见的数值崩坏问题，同时突破传统模拟游戏的创意瓶颈。

> **核心理念**：用硬编码的**生态规则**保证系统的数值平衡与稳定性，用**大语言模型（LLM）**提供无限的生物多样性与涌现式叙事。

## 🌟 核心特性

### 1. 🧠 混合演化引擎 (Hybrid Engine)
系统将演化过程拆解为两个维度，互为表里：
- **数值骨架 (The Skeleton - Rules)**：
  - 基于 **克莱伯定律 (Kleiber's Law)** 计算代谢率与能量消耗。
  - 严格的 **营养级 (Trophic Levels)** 能量传递与承载力限制。
  - 动态的 **r/K 选择理论** 决定繁殖策略。
  - **物种分级 (Tiering)**：智能区分核心物种与背景物种，优化算力分配。
- **叙事血肉 (The Flesh - AI)**：
  - LLM 负责物种的 **形态生成、命名、适应性变异**。
  - 生成地质变迁的 **史诗叙事**。
  - 创造独特的 **生态位 (Niche)** 描述与种间关系。

### 2. 🗺️ 动态六边形世界
- **126x40 六边形网格**：模拟真实的大陆板块、洋流与气候带。
- **板块构造演化**：模拟从“稳定期”到“分裂期”再到“碰撞期”的地质循环，动态生成山脉、海沟与火山。
- **环境压力**：全球变暖、海平面升降、极端干旱等事件实时重塑地图。

### 3. 🧬 深度谱系追踪
- **交互式族谱树**：完整记录物种的演化路径，清晰展示 **分化 (Speciation)**、**灭绝 (Extinction)** 与 **杂交 (Hybridization)** 事件。
- **遗传距离计算**：基于形态与基因特征计算物种间的亲缘关系，决定杂交可育性。
- **器官系统**：可视化的生物蓝图，展示物种的进化特征（如“光合作用皮层”、“喷气式推进囊”）。

### 4. 📊 生态位分析与数据可视化
- **全球趋势仪表盘 (Global Trends)**：直观展示气温、海平面、生物量与物种多样性的历史走势（Victoria 3 风格）。
- **物种总账 (Species Ledger)**：类似财务报表的物种数据管理视图。
- **向量化对比**：使用 Embedding 技术计算物种间的生态位重叠度。
- **竞争可视化**：直观展示不同物种在体型、代谢、环境适应性上的竞争关系。

### 5. 🔓 表观遗传与休眠基因
- **压力激活**：物种体内携带“休眠基因库”。当面临灭绝级压力（如突发冰期）时，特定的性状（如厚皮毛）会被瞬间激活。
- **非随机演化**：模拟生物对环境的紧急生理反应，补充了常规达尔文演化速度过慢的问题。

---

## 🚀 快速开始

本项目采用 Monorepo 结构，包含后端 (FastAPI) 和前端 (React)。

### 环境要求
- Python 3.10+
- Node.js 18+
- OpenAI API Key (或兼容的 LLM 服务)

### 1. 启动后端
后端负责核心模拟计算与数据存储。

```bash
# 1. 进入后端目录
cd backend

# 2. 创建并激活虚拟环境
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 配置环境变量
# 复制示例配置（如果存在）或直接创建 .env
# 编辑 .env 文件，填入你的 AI_API_KEY 和 AI_BASE_URL

# 5. 启动服务
uvicorn app.main:app --reload --port 8000
```
*首次启动会自动初始化 `data/db/egame.db` 并生成初始物种。*

### 2. 启动前端
前端提供可视化的上帝视角 HUD。

```bash
# 新开一个终端窗口，进入前端目录
cd frontend

# 安装依赖并启动
npm install
npm run dev
```
访问 `http://localhost:5173` 开始演化之旅。

### 3. 运行测试与调试
确保核心逻辑的稳定性。

```bash
# 运行模拟集成测试 (End-to-End Scenario)
python tests/api_simulation_test/run_test.py
```

此外，你可以在前端界面的 **"设置 -> 开发者工具"** 中直接运行系统健康检查、重置世界或测试地形演化算法。

---

## 📂 项目结构

```text
EvoSandbox/
├── backend/            # 核心演化引擎 (FastAPI + SQLModel)
│   ├── app/simulation/ # 模拟循环主逻辑
│   ├── app/services/   # 规则服务 (死亡、繁殖、地形、分级)
│   └── app/ai/         # AI 模型路由与 Prompt
├── frontend/           # 策略 HUD (React + Vite + D3.js + Recharts)
├── scripts/            # 运维与测试脚本
├── data/               # [自动生成] 存档、数据库、日志、导出文件
└── docs/               # 开发文档
```

## 📖 文档索引

- **[开发文档 (DEV_DOC.md)](DEV_DOC.md)**：深入了解混合架构的实现原理、核心算法与数据流。
- **[API 指南 (API_GUIDE.md)](API_GUIDE.md)**：后端接口定义与前端集成手册。

## 🤝 贡献

欢迎提交 Pull Request！无论是调整生态参数（让模拟更真实），还是优化 AI Prompt（让叙事更精彩），我们都非常期待。

## 📄 许可

保留所有权利。如需使用请联系作者。
