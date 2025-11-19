# Frontend Integration 指南

说明前端如何消费 API、服务层封装与 UI 依赖。

## 范围
- `frontend/src/services/api.ts` 与 `api.types.ts`
- Hooks (`frontend/src/hooks/*`)
- 关键 UI 模块（地图、物种面板、存档模态）

## 目标
- 建立 API → Service → Hook → Component 的映射，定位联调责任人。
- 提供模拟/回放时的 mock 策略。

## 子文档

| 文档 | 内容 |
| --- | --- |
| [services-layer.md](services-layer.md) | `api.ts` 函数映射 |
| [state-hooks.md](state-hooks.md) | Hooks 与状态管理 |
| [ui-modules.md](ui-modules.md) | UI 组件依赖关系 |

维护人：Frontend Team。
