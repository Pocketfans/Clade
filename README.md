# 🦎 Clade - AI 演化沙盒  （中文名征集中）

> **在这个游戏里，你是上帝。**
>
> 创造生命，释放天灾，然后看着它们努力活下去（或者灭绝）。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" />
  <img src="https://img.shields.io/badge/Node.js-18+-green?logo=nodedotjs" />
  <img src="https://img.shields.io/badge/AI-DeepSeek%20%7C%20GPT%20%7C%20Claude-purple" />
  <img src="https://img.shields.io/badge/Tensor-NumPy%20%2B%20SciPy-orange" />
</p>

---

## 🎮 这是什么？

**Clade** 是一个 AI 驱动的生物演化模拟器。想象一下《孢子》遇上《环世界》，再加上一个会讲故事的 AI —— 就是这个感觉。

你可以：
- 🌍 **创造世界** - 一张由 128×40 个六边形组成的动态地图
- 🧬 **设计生命** - AI 会帮你生成独特的生物，有名字、有器官、有性格
- ☄️ **降下天灾** - 火山爆发、冰河期、陨石撞击...看谁能挺过去
- 📊 **见证演化** - 数百万年的进化在几分钟内上演，族谱树实时更新

每次游戏都是独一无二的故事。你的"三眼喷墨章鱼"可能会统治海洋，也可能被一群"光合作用甲壳蟹"取而代之，甚至还可能演化出……猫娘？

---

## 🚀 5 分钟上手

### 第一步：安装必备软件

> ⚠️ **重要提示**：本游戏需要同时安装 **Python** 和 **Node.js**，两者缺一不可！

如果你还没有安装，请先下载安装：
注意！！目前只支持python3.12，请下载对应版本的python安装
| 软件 | 版本要求 | 下载链接 |
|------|---------|----------|
| **Python** | 3.12 | [👉 点击下载](https://www.python.org/downloads/) |
| **Node.js** | 18 或更高 | [👉 点击下载](https://nodejs.org/zh-cn) |

<details>
<summary>📖 安装小贴士（点击展开）</summary>

#### Windows 用户

**安装 Python：**
1. 点击上面的链接，下载3.12.x版本的 Python（如果已经安装新版本没事，启动脚本会自动识别3.12版本的Python）
2. 运行安装程序时，**一定要勾选 "Add Python to PATH"**（这很重要！）
3. 点击 "Install Now" 完成安装

**安装 Node.js：**
1. 点击上面的链接，下载 LTS（长期支持）版本
2. 一路点击 "Next" 完成安装即可

**验证安装：**
打开命令提示符（按 `Win+R`，输入 `cmd`，回车），输入：
```
python --version
node --version
```
如果都显示版本号，说明安装成功！

#### Mac 用户（未经测试）

推荐使用 Homebrew 安装：
```bash
brew install python@3.12 node
```

#### Linux 用户

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3.12-venv nodejs npm

# Fedora
sudo dnf install python3.12 nodejs
```

</details>

### 第二步：下载游戏

**方式 A：直接下载（推荐新手）**
1. 点击页面右上角绿色的 `Code` 按钮
2. 选择 `Download ZIP`
3. 解压到你喜欢的位置

**方式 B：使用 Git**
```bash
git clone https://github.com/Pocketfans/Clade.git
cd Clade
```

### 第三步：启动游戏

#### 🪟 Windows 用户（超简单！）

双击 `start.bat`，自动完成安装和启动！

启动器会自动：
- ✅ 检查 Python 和 Node.js
- ✅ 安装所有依赖
- ✅ 启动后端和前端服务
- ✅ 打开浏览器

<details>
<summary>📖 一键脚本不工作？点击查看手动启动方法</summary>

**第一步：启动后端**

```powershell
# 进入项目目录（改成你自己的路径）
cd C:\你的路径\Clade

# 进入后端目录
cd backend

# 创建虚拟环境（只需第一次）
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1
# 如果是 CMD 命令提示符，用这个：
# .\venv\Scripts\activate.bat

# 安装依赖（只需第一次）
pip install -e ".[dev]"

# 启动后端服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8022
```

**第二步：启动前端**

**新开一个** PowerShell 或命令提示符窗口，运行：

```powershell
# 进入项目目录（改成你自己的路径）
cd C:\你的路径\Clade

# 进入前端目录
cd frontend

# 安装依赖（只需第一次）
npm install

# 启动前端服务
npm run dev
```

**第三步：访问游戏**

打开浏览器，访问：**http://localhost:5188**

> 💡 **提示**：
> - 两个窗口都要保持打开状态，关闭任意一个都会导致服务停止
> - 如果端口 8022 或 5188 被占用，可以在 `.env` 文件中修改

</details>

#### 🍎 Mac / 🐧 Linux 用户（未经测试）

打开终端，依次运行：

```bash
# 1. 启动后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8022 &

# 2. 启动前端（新开终端窗口）
cd frontend
npm install
npm run dev
```

然后打开浏览器访问：**http://localhost:5188**

---

## 🔑 配置 AI（必须！）

游戏需要 AI 服务来生成物种和叙事。

> ⚠️ **重要提示**：本游戏需要两种 AI 模型：
> - **Chat 模型**：用于生成物种描述、叙事文本
> - **Embedding 模型**：用于物种特征向量化（可选但推荐）

### 推荐服务商

| 服务商 | 特点 | 注册链接 |
|--------|------|----------|
| **硅基流动** | 🌟 强烈推荐！支持 Chat + Embedding，国内稳定 | [👉 注册](https://cloud.siliconflow.cn/) |
| **DeepSeek** | 便宜好用，中文优秀 | [👉 注册](https://platform.deepseek.com/) |
| **OpenAI** | GPT 系列 | [👉 注册](https://platform.openai.com/) |
| **Google AI** | Gemini  | [👉 注册](https://aistudio.google.com/) |
| **Anthropic** | Claude  | [👉 注册](https://console.anthropic.com/) |

### 配置步骤

1. 游戏启动后，点击右上角的 **⚙️ 设置**
2. 找到 **"AI 配置"** 部分
3. 选择你注册的服务商，填入 API Key
4. 点击 **"测试连接"** 确认可用
5. 保存！

> 💡 **小贴士**：物叙述模型尽量选择便宜且延迟低的，不太需要推理能力。所以比如gemini 2.5flash和gpt5.1 mini这种类型是首选。Deepseek chat也可以，主要是非常便宜。

---

## 🎯 游戏玩法

### 🌟 核心循环

在这个世界里，时间以"回合"为单位流逝。每一回合代表着数千年甚至上百万年的岁月。

1. **环境变迁** 🌧️
   - 海平面升降、气温波动、降水变化
   - 板块漂移（可选）：大陆分裂与合并改变生物迁徙路线
   
2. **生存竞争** 🦁
   - **食物网**：捕食者追逐猎物，草食动物寻找植被
   - **迁徙**：动物为生存寻找更适宜的栖息地
   - **死亡**：饥饿、寒冷、酷热、被捕食...只有最适者生存

3. **演化与变异** 🧬
   - **地理隔离**：张量系统检测种群分布的不连通区域
   - **生态分歧**：同一物种在不同环境中产生分化压力
   - **物种分化**：AI 为新物种生成名称、描述、器官演化
   - **杂交**：相近物种相遇产生混种后代

4. **AI 叙事** 🤖
   - AI 观察世界，为新物种命名，记录兴衰历史

### 🎮 上帝的工具箱

| 功能 | 描述 |
|------|------|
| **推进时间** | 点击"下一回合"，看着沧海桑田在指尖流转 |
| **降下天灾** | **陨石撞击**、**冰河世纪**、**火山爆发** |
| **物种透视** | 点击任意物种，查看详细档案 |
| **族谱追踪** | 打开全景族谱树，追溯祖先 |
| **生态分析** | 查看物种竞争关系和生态位分布 |
| **平行世界** | 利用存档功能分叉不同时间线 |

---

## 🏗️ 系统架构

### 模拟流水线阶段

```
回合开始
    │
    ├── 初始化 & 压力解析
    │
    ├── 地图演化（海平面、气候）
    │
    ├── 物种分档（Critical/Focus/Background）
    │       ├── Critical: 高优先级关键物种
    │       ├── Focus: 中优先级关注物种
    │       └── Background: 低优先级背景物种
    │
    ├── 生态拟真（Allee效应、疾病、共生）
    │
    ├── 张量死亡率计算
    │       ├── 温度适应性
    │       ├── 竞争压力
    │       └── 食物网影响
    │
    ├── 迁徙 & 扩散
    │
    ├── 种群更新（死亡 + 繁殖）
    │
    ├── 张量分化检测
    │       ├── 地理隔离检测（scipy.ndimage.label）
    │       └── 生态分歧检测（环境方差）
    │
    ├── 物种分化（AI 生成）
    │       ├── 非背景物种 → LLM 生成
    │       └── 背景物种 → 规则引擎生成
    │
    ├── 报告生成 & 保存
    │
回合结束
```

### LLM 功能模块

| 功能 | 说明 | Token 消耗 |
|------|------|-----------|
| `speciation` | 单物种分化 | 中 |
| `speciation_batch` | 批量动物分化 | 高（批量处理） |
| `plant_speciation_batch` | 批量植物分化 | 高（批量处理） |
| `hybridization` | 杂交生成 | 中 |
| `forced_hybridization` | 强行杂交 | 中 |
| `turn_report` | 回合叙事 | 低（本地模板） |

### 性能控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_speciation_per_turn` | 20 | 每回合 AI 分化上限 |
| `max_deferred_requests` | 60 | 排队任务上限 |
| `batch_size` | 3 | 每批次物种数 |
| `max_concurrent` | 10 | 最大并发批次 |




### 可配置参数

| 分类 | 参数 | 说明 |
|------|------|------|
| **开关** | `use_tensor_mortality` | 张量死亡率计算 |
| | `use_tensor_speciation` | 张量分化检测 |
| | `use_auto_tradeoff` | 自动代价权衡 |
| **温度** | `temp_optimal` | 最适温度 |
| | `temp_tolerance` | 温度容忍度 |
| **种群** | `diffusion_rate` | 扩散率 |
| | `birth_rate_base` | 基础出生率 |
| | `competition_strength` | 竞争强度 |
| **分化** | `divergence_threshold` | 分歧检测阈值 |

---

## ❓ 常见问题

<details>
<summary><b>Q: 双击 start.bat 没反应？</b></summary>

1. 确保 Python 3.12 和 Node.js 已正确安装
2. 右键 `start.bat`，选择"以管理员身份运行"
3. 如果还不行，手动运行命令（见上方手动启动说明）

</details>

<details>
<summary><b>Q: 报错说端口被占用？</b></summary>

双击 `stop.bat` 关闭所有服务，然后重新启动。

或者修改端口：
- 后端：编辑 `.env` 文件，修改 `BACKEND_PORT=8022`
- 前端：在 `frontend/vite.config.ts` 中修改端口

</details>

<details>
<summary><b>Q: AI 返回空白/报错？</b></summary>

1. 检查 API Key 是否正确
2. 检查账户余额是否充足
3. 尝试切换其他模型或服务商

</details>

<details>
<summary><b>Q: 后期物种太多，分化会消耗很多 Token 吗？</b></summary>

不会！系统有多重保护：
- 张量分化检测 = **0 Token**（纯数学计算）
- 背景物种分化 = **0 Token**（规则引擎生成）
- 每回合 AI 分化上限 = **最多 20 个物种**
- 超出上限的任务会排队或被丢弃

</details>

<details>
<summary><b>Q: 可以离线玩吗？</b></summary>

如果你在本机上部署了embedding模型和chat模型，可以离线游玩。否则还是推荐在线使用ai服务。

</details>

---

## 📁 项目结构

```
Clade/
├── start.bat              # 🚀 Windows 一键启动
├── stop.bat               # 🛑 关闭所有服务
├── backend/               # 后端引擎（Python）
│   ├── app/
│   │   ├── ai/            # AI 路由与提示词
│   │   ├── simulation/    # 模拟流水线
│   │   ├── tensor/        # 张量计算系统
│   │   └── services/      # 业务服务
│   └── pyproject.toml
├── frontend/              # 前端界面（React）
│   ├── src/
│   │   ├── components/    # UI 组件
│   │   └── services/      # API 服务
│   └── package.json
├── data/                  # 存档和配置
└── docs/                  # 开发文档
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.12 + FastAPI + SQLModel |
| **张量计算** | NumPy + SciPy |
| **AI 集成** | OpenAI API 兼容（DeepSeek/GPT/Claude） |
| **前端框架** | React 18 + TypeScript + Vite |
| **可视化** | D3.js + CSS Glassmorphism |
| **数据库** | SQLite |

---

## 👋 写在后面

大家好，我是 **幻想口袋**

📺 **B站主页**：[https://space.bilibili.com/2965629](https://space.bilibili.com/2965629)

说实话，这个项目是我面向AI编程的，虽然整体架构基本上都是我自己设计的，但代码的大部分都是 AI 辅助生成的。

所以，这个项目肯定有很多问题和 bug。 

我没法保证代码有多优雅，架构有多合理。但我希望大家能在这个项目中体会到物种演化的神奇和乐趣，这也是我的初衷。

**如果你也喜欢这个项目，非常欢迎你来帮忙！**

---

## 🤝 参与贡献

1. **提 Issue**：发现 bug 或有建议，直接开 Issue
2. **提 PR**：修复问题或添加功能，欢迎提交 PR
3. **讨论**：对项目有任何想法，可以在 Discussions 里聊

不管贡献大小，我都非常感谢！🙏

---

## 📬 联系我

- **B站**：[幻想口袋](https://space.bilibili.com/2965629)
- **GitHub Issues**：有问题直接提 Issue

---

## 📄 开源协议

**AGPL-3.0 (后端) + MPL-2.0 (前端)**

| 组件 | 许可证 | 说明 |
|------|--------|------|
| `backend/` | AGPL-3.0 | 后端核心代码 |
| `frontend/` | MPL-2.0 | 前端界面代码 |
| `docs/`, `*.md` | CC-BY-4.0 | 文档 |
| `data/`, `*.json`, `*.yaml` | MIT | 配置与数据 |

详见 [LICENSE](LICENSE) 文件

---

<p align="center">
  <b>让生命自由演化，让 AI 讲述故事。</b>
  <br><br>
  这是一个用爱发电的项目，如果觉得有趣，请给个 ⭐ Star 支持一下！
</p>
