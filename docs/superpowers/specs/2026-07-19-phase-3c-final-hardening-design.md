# Phase 3C 最终稳健性收尾设计

**日期：** 2026-07-19  
**状态：** 已获用户批准，等待书面设计复核  
**对应分支：** `phase-2c-outbound-url-security`  
**对应 PR：** Pocketfans/Clade #15（继续保持 Draft）

## 1. 背景

Phase 3B 已完成端到端请求预算、流式中断状态、降级提示与最终安全验收。最终独立复审没有发现 Critical 或 Important 问题，但留下了 7 条不阻塞发布的 Minor 建议。这些建议不会影响当前功能正确性，却能降低以后重构、测试卡死和旧扩展兼容失败的风险。

Phase 3C 只收口这 7 条建议，不扩展产品功能，不改变 AI 路由策略、服务商选择、重试次数、退避公式、游戏规则、模拟公式、数据库或存档格式。

## 2. 目标

1. 用明确的内部契约识别已经脱敏的网络关闭错误，移除对私有类名、函数名和调用栈结构的猜测。
2. 将包含排队等待的诊断文案从“处理耗时”改为“总耗时”，保持计算方式和路由统计完全不变。
3. 直接锁定流式请求默认 600 秒硬时限和非法时限拒绝规则。
4. 证明非字符串流内容不会把 `content_started` 误置为 `True`。
5. 给一个可能无限等待的异步测试增加测试专用超时。
6. 保证同步和异步后台运行器在 `timeout <= 0` 时不会启动工作线程。
7. 让没有声明 `uses_internal_request_budget` 的旧式、鸭子类型 Stage 继续使用管线通用超时，而不是因缺少属性报错。

## 3. 方案对比

### 方案 A：完整、行为保持型收尾（采用）

处理全部 7 条建议。生产代码只增加明确契约、零预算预检、兼容回退和诊断文案修正；其余工作全部是精确测试。优点是一次清完已知技术债，且不改变业务结果。代价是需要重新跑后端、前端和安全验收。

### 方案 B：只改文案和补测试

只处理可见文案与三类测试缺口。代码改动最少，但私有调用栈耦合、零预算线程启动和旧 Stage 兼容风险仍然存在。

### 方案 C：保持 Phase 3B 现状

不增加任何改动，最快进入审查，但 7 条 Minor 会继续留在审查记录中。

用户选择方案 A，并明确选择“处理耗时”改名为“总耗时”，不改变数值算法。

## 4. 总体设计原则

- **保持行为：** 不改变正常请求结果、错误码、公开错误消息、超时默认值和统计决策。
- **先测试后实现：** 每个生产修正先加入能失败的回归测试，再做最小实现。
- **失败时不启动工作：** 已经没有时间的任务必须在获得线程槽位或创建线程之前失败。
- **向后兼容：** 新的 Stage 属性对现有基类是明确契约，对旧式 Stage 则按 `False` 处理。
- **不泄露原始异常：** 关闭错误契约只能传递布尔标记，不能把上游异常文本写入日志、事件或公开响应。
- **保持 Draft：** Phase 3C 可以更新现有 PR，但不能合并或标记 Ready for review，除非用户另行确认。

## 5. 组件设计

### 5.1 已脱敏关闭错误契约

**涉及文件：**

- `backend/app/security/pinned_transport.py`
- `backend/app/security/runtime_http.py`
- `backend/app/security/tests/test_pinned_transport.py`
- `backend/app/security/tests/test_runtime_http.py`

当前 `runtime_http.py` 的 `_is_sanitized_close_error()` 会检查 traceback 中的模块名、函数名和私有类名。任何无关重命名都可能破坏识别。

设计改为由 pinned transport 在创建本地、固定公开消息的关闭错误时附加一个模块公开的内部布尔标记，并提供公开判断函数。`runtime_http.py` 只接受同时满足以下条件的错误：

1. 错误的精确类型仍是 `httpcore.NetworkError`；
2. 判断函数确认内部标记为 `True`。

判断过程不再读取 traceback、模块名、函数名或私有类名。标记不包含错误文本、URL、密钥、请求体或响应体。现有的 traceback/context/cause 清理逻辑、调用者取消优先级和固定公开错误码保持不变。

回归测试必须证明：正确标记的本地关闭错误仍能走清理恢复路径；普通 `httpcore.NetworkError` 不能伪装成该路径；原始异常哨兵不会进入公开结果和日志。

### 5.2 “总耗时”诊断文案

**涉及文件：**

- `backend/app/ai/model_router.py`
- `backend/app/ai/tests/test_model_router_security.py`

成功诊断中的“处理耗时”改为“总耗时”。`process_start`、`process_time`、`provider_call_start` 和 `provider_latency` 的计算保持原样。

因此：

- 面向诊断的“总耗时”仍包含本次尝试的排队等待和上游处理；
- 用于 `least_latency` 路由的 provider latency 仍只统计真正的服务商调用；
- 不改变服务商排序、成功计数、超时计数或返回结果。

测试分别断言新文案存在、旧文案不存在，并继续证明 provider latency 排除排队时间。

### 5.3 StreamBudget 默认值与非法输入

**涉及文件：**

- `backend/app/security/tests/test_deadline.py`

不修改 `StreamBudget` 实现。新增直接测试锁定：

- 未传 `hard_timeout` 时，硬截止点恰好等于开始时间加 600 秒；
- `idle_timeout` 或 `hard_timeout` 为 `0`、负数、`NaN`、正无穷或负无穷时抛出 `ValueError`；
- 有效的有限正数继续被接受。

这些测试把已有 `_positive_finite()` 行为从间接覆盖提升为公开回归契约。

### 5.4 非字符串流内容不算有效内容

**涉及文件：**

- `backend/app/ai/tests/test_model_router_security.py`

扩展现有 OpenAI、Anthropic、Google 三种非字符串内容参数化测试。测试显式传入一个可观察的 `StreamBudget`，并在请求结束后断言：

- 返回固定的无效响应结果；
- 没有伪造 `completed` 终态；
- `budget.content_started is False`；
- 哨兵不出现在公开事件或日志。

不修改生产解析逻辑，除非新增测试暴露与既有契约不一致的行为。

### 5.5 测试等待的失败上限

**涉及文件：**

- `backend/app/ai/tests/test_streaming_helper.py`

将裸 `await router.started.wait()` 包装在短小、仅测试使用的 `asyncio.wait_for()` 中。超时时测试必须明确失败，不能无限挂起。该超时不进入生产代码，也不改变真实请求时限。

### 5.6 零预算后台运行器

**涉及文件：**

- `backend/app/security/bounded_runner.py`
- `backend/app/security/tests/test_bounded_runner.py`

`run()` 与 `arun()` 在任何槽位获取或线程创建之前检查 `timeout <= 0`，立即抛出 `TimeoutError`。正数时限继续使用同一单调时钟截止点，线程上限仍为 4，已经启动的超时线程仍按现有方式在后台自行结束并释放槽位。

同步和异步测试都必须证明：

- `timeout=0` 和负数会抛出 `TimeoutError`；
- operation 没有被调用；
- `max_active` 保持 0；
- 正数时限的成功、异常、超时和取消行为没有回归。

### 5.7 旧式 Stage 兼容回退

**涉及文件：**

- `backend/app/simulation/pipeline.py`
- `backend/app/simulation/tests/test_pipeline.py`

管线读取预算归属时使用等价于 `getattr(stage, "uses_internal_request_budget", False)` 的兼容逻辑：

- 明确为 `True` 的 10 个 AI/Embedding 阶段继续绕过通用 stage timeout，由请求层拥有完整预算；
- 明确为 `False` 的业务阶段继续使用通用 stage timeout；
- 没有该属性的旧式 Stage 按 `False` 处理，也继续使用通用 stage timeout。

新增一个不继承 `BaseStage`、但满足旧执行接口的测试 Stage，证明缺少属性不会触发 `AttributeError`，并且超时仍能取消该阶段。现有 `Stage` Protocol 与 `BaseStage` 默认值保持不变。

## 6. 数据与控制流

1. 请求进入 ModelRouter 后继续使用 Phase 3B 的单一 caller-owned budget。
2. 异步请求排队和服务商调用的计时点不变；只修改成功诊断名称。
3. 网络流关闭时，pinned transport 创建固定、脱敏的本地错误并设置内部标记。
4. runtime client 通过类型加标记识别该错误，执行既有的清理优先级和公开错误映射。
5. 阻塞操作只有在时限为正且取得槽位后才能启动线程。
6. 模拟管线仅在 Stage 未拥有内部预算时添加通用 stage timeout；缺少新属性等同于未拥有。

## 7. 错误处理与安全边界

- 所有新增失败仍复用 `TimeoutError`、`ValueError`、`OutboundRequestError` 和既有固定公开消息。
- 不新增包含上游异常文本的日志或事件。
- 不记录 API Key、Authorization header、请求体、响应体或完整查询目标。
- 调用者取消仍优先于内部关闭错误；清理错误不能替换原始业务或安全错误。
- 零预算检查只阻止本不应启动的任务，不尝试强制终止已运行线程。

## 8. 测试与验收

### 8.1 精确回归测试

- `test_deadline.py`：600 秒默认值、非法 idle/hard 输入。
- `test_bounded_runner.py`：同步/异步零和负时限不启动 operation。
- `test_runtime_http.py` 与 `test_pinned_transport.py`：关闭错误标记、清理优先级、脱敏。
- `test_model_router_security.py`：总耗时文案、provider latency 不变、非字符串内容不标记开始。
- `test_streaming_helper.py`：测试等待有失败上限。
- `test_pipeline.py`：旧式 Stage 缺少属性时继续使用通用超时。

### 8.2 完整质量门

- Phase 3C 相关后端测试全部通过。
- 后端全量测试通过，既有 skip/warning 数量不增加。
- 前端 85 项基线测试通过。
- ESLint 0 errors，warning 不超过既有 162 条基线。
- TypeScript `--noEmit` 通过。
- Vite 生产构建通过。
- `git diff --check` 通过。
- 敏感信息和竞争计时器静态/动态审计通过。
- 独立复审为 0 Critical、0 Important；新的 Minor 必须记录并由主代理判断是否阻塞。

## 9. 明确不做的内容

- 不改变 60 秒流空闲时限或 600 秒流硬时限。
- 不改变普通 JSON 请求时限、队列规则、并发上限、重试次数或退避公式。
- 不重构 ModelRouter 的总体结构。
- 不修改前端文案或页面布局。
- 不修改游戏规则、模拟阶段顺序、数据库、存档或依赖版本。
- 不合并 PR，不标记 Ready for review，不删除分支或 worktree。

## 10. 风险与控制

- **关闭错误标记被误用：** 继续要求精确 `httpcore.NetworkError` 类型，并用普通未标记错误的反向测试保护。
- **零时限语义变化：** 只影响本来已经没有执行预算的调用；正数时限走原路径并运行完整兼容测试。
- **旧 Stage 回退掩盖拼写错误：** 只有缺少属性时回退为更保守的通用超时；内置 Stage 的 10 个 `True` 所有者继续由精确清单测试保护。
- **诊断文案影响日志断言：** 只更新精确文案测试，不改变结构化统计字段或决策输入。

## 11. 完成定义

Phase 3C 只有在以下条件全部满足时才算完成：7 条 Minor 均有明确代码或测试落点；所有质量门通过；独立复审没有 Critical 或 Important；设计、实施计划和验证证据齐全；分支已推送到现有 fork；PR #15 指向最终提交且仍为 Draft、open、unmerged。
