# 🦎 Clade - AI 演化沙盒  （中文名待定）

> **在这个游戏里，你是上帝。**
>
> 创造生命，释放天灾，然后看着它们努力活下去（或者灭绝）。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" />
  <img src="https://img.shields.io/badge/Node.js-18+-green?logo=nodedotjs" />
  <img src="https://img.shields.io/badge/AI-DeepSeek%20%7C%20GPT%20%7C%20Claude-purple" />
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
> - **Python** 用于运行后端模拟引擎和 AI 服务
> - **Node.js** 用于运行前端界面

如果你还没有安装，请先下载安装：

| 软件 | 版本要求 | 下载链接 |
|------|---------|----------|
| **Python** | 3.11 或更高 | [👉 点击下载](https://www.python.org/downloads/) |
| **Node.js** | 18 或更高 | [👉 点击下载](https://nodejs.org/zh-cn) |

<details>
<summary>📖 安装小贴士（点击展开）</summary>

#### Windows 用户

**安装 Python：**
1. 点击上面的链接，下载最新版 Python
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

#### Mac 用户

推荐使用 Homebrew 安装：
```bash
brew install python@3.11 node
```

#### Linux 用户

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv nodejs npm

# Fedora
sudo dnf install python3.11 nodejs
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

双击 `start.bat`，就直接自动化安装完成了！

启动器会自动：
- ✅ 检查 Python 和 Node.js
- ✅ 安装所有依赖
- ✅ 启动后端和前端服务
- ✅ 打开浏览器

#### 🍎 Mac / 🐧 Linux 用户

打开终端，依次运行：

```bash
# 1. 启动后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000 &

# 2. 启动前端（新开一个终端窗口）
cd frontend
npm install
npm run dev
```

然后打开浏览器访问：**http://localhost:5173**

---

## 🔑 配置 AI（必须！）

游戏需要 AI 服务来生成物种和叙事。别担心，设置很简单：

> ⚠️ **重要提示**：本游戏需要两种 AI 模型：
> - **Chat 模型**（对话模型）：用于生成物种描述、叙事文本等
> - **Embedding 模型**（嵌入模型）：用于物种特征向量化、语义分析等
> 
> 请确保你选择的 AI 服务商同时支持这两种模型！

### 首选推荐：硅基流动

|--------|------|----------|
| **硅基流动** |  **强烈推荐！** 同时提供 Chat 模型和 Embedding 模型| [👉 注册](https://cloud.siliconflow.cn/) |

> 💡 **为什么推荐硅基流动？**
> - ✅ 同时支持 Chat 和 Embedding 两种模型类型（本游戏必需）且提供免费的Embedding模型
> - ✅ 提供多种模型选择（DeepSeek、Qwen、GLM 等）
> - ✅ 国内访问稳定，无需科学上网

### 其他选择（国内用户友好）

| 服务商 | 特点 | 注册链接 |
|--------|------|----------|
| **DeepSeek** | 便宜好用，中文优秀（需搭配其他 Embedding 服务） | [👉 注册](https://platform.deepseek.com/) |
| **火山引擎** | 豆包大模型 | [👉 注册](https://www.volcengine.com/product/doubao) |

### 国际用户

| 服务商 | 特点 | 注册链接 |
|--------|------|----------|
| **OpenAI** | GPT-5 强大但贵 | [👉 注册](https://platform.openai.com/) |
| **Google AI** | Gemini 免费额度多 | [👉 注册](https://aistudio.google.com/) |
| **Anthropic** | Claude 思维清晰 | [👉 注册](https://console.anthropic.com/) |

### 配置步骤

1. 游戏启动后，点击右上角的 **⚙️ 设置**
2. 找到 **"AI 服务"** 部分
3. 选择你注册的服务商
4. 填入 API Key
5. 点击 **"测试连接"** 确认可用
6. 保存！

> 💡 **小贴士**：DeepSeek v3.2 是性价比之王，前期一回合甚至不到1分钱，够玩很久了！

---

## 🎯 游戏玩法

### 基础操作

| 操作 | 说明 |
|------|------|
| **推进回合** | 点击主界面的"下一回合"按钮，时间前进 |
| **查看物种** | 点击地图上的六边形，查看该地区的物种 |
| **族谱树** | 在侧边栏查看物种的演化历史 |
| **释放压力** | 点击"压力"按钮，选择灾难类型释放 |

### 进阶玩法

- **自定义物种**：在设置中创建你自己设计的始祖生物
- **地质演变**：开启板块漂移，看大陆分分合合
- **生态分析**：使用向量对比功能分析物种间的竞争关系
- **导出数据**：将演化历史导出为报告，分享给朋友

---

## ❓ 常见问题

<details>
<summary><b>Q: 双击 start.bat 没反应？</b></summary>

1. 确保 Python 和 Node.js 已正确安装
2. 右键 `start.bat`，选择"以管理员身份运行"
3. 如果还不行，手动运行命令（见上方手动启动说明）

</details>

<details>
<summary><b>Q: 报错说端口被占用？</b></summary>

可能是上次没有正确关闭。双击 `stop.bat` 关闭所有服务，然后重新启动。

或者修改端口：
- 后端：在 `start.ps1` 中修改 `--port 8000`
- 前端：在 `frontend/vite.config.ts` 中修改端口

</details>

<details>
<summary><b>Q: AI 返回空白/报错？</b></summary>

1. 检查 API Key 是否正确
2. 检查账户余额是否充足
3. 尝试切换其他模型或服务商

</details>

<details>
<summary><b>Q: 如何重置世界？</b></summary>

进入游戏后，点击 **设置 → 开发者工具 → 重置世界**。

或者直接删除 `data/` 文件夹下的所有内容（保留 `settings.example.json`）。

</details>

<details>
<summary><b>Q: 可以离线玩吗？</b></summary>

游戏本身可以离线运行，但物种生成和叙事需要 AI 服务。没有 AI 的话，演化会使用简化规则，但会少很多乐趣。

</details>

---

## 📁 文件说明

```
Clade/
├── start.bat          # 🚀 Windows 一键启动
├── stop.bat           # 🛑 关闭所有服务
├── backend/           # 后端引擎（Python）
├── frontend/          # 前端界面（React）
├── data/              # 存档和配置（游戏生成）
│   └── settings.example.json  # 配置模板
└── docs/              # 开发文档
```

---

## 🛠️ 开发者信息

想深入了解技术细节？查看：

- [开发文档](DEV_DOC.md) - 架构设计与核心算法
- [API 指南](API_GUIDE.md) - 接口文档
- [模块文档](docs/api-guides/README.md) - 各模块详细说明

### 技术栈

- **后端**：Python 3.11 + FastAPI + SQLModel + NumPy
- **前端**：React + TypeScript + Vite + D3.js
- **AI**：支持 OpenAI API 兼容的任何服务


---

## 👋 写在后面

大家好，我是 **幻想口袋**

📺 **B站主页**：[https://space.bilibili.com/2965629](https://space.bilibili.com/2965629)

说实话，这个项目从一开始就是我面向AI编程的，虽然整体架构基本上都是我自己设计的，但代码的大部分都是 AI 辅助生成的。

所以，这个项目肯定有很多问题和 bug。 

我没法保证代码有多优雅，架构有多合理。但我希望大家能在这个项目中体会到物种演化的神奇和乐趣，这也是我的初衷。

**如果你也喜欢这个项目，非常欢迎你来帮忙！** 不管是：
- 🔧 修复一个 bug
- ✨ 优化一段代码
- 📝 完善一处文档
- 💡 提出一个建议

对我来说都是莫大的帮助。这个项目是开源的，属于每一个愿意参与的人。
---

## 🤝 参与贡献

因为这是一个 AI 辅助开发的项目，代码中难免存在各种问题：
- 可能有些地方逻辑不够严谨
- 可能有些代码风格不够统一
- 可能有些功能实现得不够优雅

**但这正是开源的意义所在** —— 集众人之力，让它变得更好。

如果你愿意帮忙，可以：
1. **提 Issue**：发现 bug 或有建议，直接开 Issue 告诉我
2. **提 PR**：如果你修复了问题或添加了功能，欢迎提交 PR
3. **讨论**：对项目有任何想法，可以在 Discussions 里聊

不管贡献大小，我都非常感谢！🙏

---

## 📬 联系我

- **B站**：[幻想口袋](https://space.bilibili.com/2965629) - 会发布项目相关视频和更新
- **GitHub Issues**：有问题直接提 Issue，我会尽量回复

---

## 📄 开源协议

**MIT License + Commons Clause**

本项目采用 MIT 许可证，附加 Commons Clause 条款：

✅ **你可以**：
- 自由使用、学习、修改代码
- 在非商业项目中使用
- 基于此项目创建衍生作品
- 贡献代码回馈社区

❌ **但不可以**：
- 销售本软件或其副本
- 提供基于本软件的付费服务（托管、咨询等）
- 将本软件作为付费产品的核心功能



---

<p align="center">
  <b>让生命自由演化，让 AI 讲述故事。</b>
  <br><br>
  这是一个用爱发电的项目，如果觉得有趣，请给个 ⭐ Star 支持一下！
</p>
