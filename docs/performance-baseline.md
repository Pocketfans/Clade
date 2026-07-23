# 性能基线

这份基线用来回答一个简单问题：代码改动后，Clade 的核心回合流程是否明显变慢、占用更多内存，或产生更多数据库写入。

它是可重复比较的工程证据，不是对所有电脑性能的承诺。不同硬件、操作系统或 Python 版本产生的结果不能直接横向比较。

## 当前基线

正式数据保存在 [`docs/performance/baseline-v1.json`](performance/baseline-v1.json)，由提交
`1c79d1690ea110b0d65b2a2b7eb635718f2114a6` 的测量工具生成。

生成环境：

- Windows 11，Python 3.12.10
- 16 个逻辑处理器
- NVIDIA GeForce RTX 2080（8192 MiB）
- 固定随机种子：42

| 场景 | 物种数 | 回合数 | 总耗时 | Python 峰值内存 | 数据库写语句 | 存档大小 | 保存耗时 | 读取耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `scale-10` | 10 | 1 | 278.1 ms | 1.44 MiB | 22 | 2,168 B | 39.6 ms | 186.5 ms |
| `scale-100` | 100 | 1 | 1,376.5 ms | 3.02 MiB | 112 | 11,437 B | 88.6 ms | 1,216.1 ms |
| `scale-500` | 500 | 1 | 5,481.0 ms | 7.58 MiB | 512 | 51,600 B | 341.0 ms | 4,916.4 ms |
| `seeded-100-turn` | 10 | 100 | 2,451.4 ms | 2.17 MiB | 220 | 2,205 B | 36.4 ms | 181.4 ms |

所有场景的 AI 调用数均为 0。详细的 CPU 时间、数据库变更行数和每个 Stage 的耗时保留在 JSON 文件中。

## 安全边界

每个场景都在独立的 Python 子进程中运行，并使用新的临时数据库、临时存档目录和临时输出文件。运行结束后会自动清理这些临时文件，不会读取或改写正常游戏数据库和玩家存档。

子进程不会继承名称中含有 `API_KEY`、`TOKEN`、`SECRET` 或 `PASSWORD` 的环境变量，并会关闭 AI、嵌入和文件日志。场景还会验证数据库为空、路径位于隔离工作目录中；不满足条件时直接停止。

## 生成一份新报告

先在仓库根目录取得当前完整提交编号：

```powershell
git rev-parse HEAD
```

然后进入 `backend` 目录，在项目虚拟环境中运行：

```powershell
python -m app.simulation.performance_benchmark generate `
  --output ..\docs\performance\current.json `
  --commit-sha <上一步显示的完整提交编号>
```

工具默认拒绝覆盖已有文件。确实需要覆盖时才添加 `--overwrite`。

## 与正式基线比较

在 `backend` 目录运行：

```powershell
python -m app.simulation.performance_benchmark compare `
  --baseline ..\docs\performance\baseline-v1.json `
  --current ..\docs\performance\current.json
```

退出码含义：

- `0`：环境和场景可比较，没有发现超过阈值的退化；
- `1`：可比较，但至少一项指标超过退化阈值；
- `2`：报告格式、场景或环境不兼容，不能得出性能结论。

比较器使用版本化 JSON 约定，并为有自然波动的时间和内存指标保留相对阈值与最小绝对容差。更新正式基线时，应先解释差异原因并经过审查，不能只因为新结果更慢就覆盖旧基线。
