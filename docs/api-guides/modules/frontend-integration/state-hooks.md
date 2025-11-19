# State Hooks 映射

描述 `frontend/src/hooks` 中各 Hook 如何消费服务层及 API。

| Hook | 文件 | 依赖 API | 功能 |
| --- | --- | --- | --- |
| `useGameState` | `hooks/useGameState.ts` | `runTurn`, `fetchHistory`, `fetchQueueStatus`, `fetchMapOverview` | 管理全局模拟状态、最近报告、地图缓存 |
| `usePressure` | `hooks/usePressure.ts` | `fetchPressureTemplates`, `addQueue`, `clearQueue` | 压力选择与排队控制 |
| `useSelection` | `hooks/useSelection.ts` | `fetchSpeciesDetail`, `fetchLineageTree` | 物种/谱系选择状态 |
| `useSession` | `hooks/useSession.ts` | `fetchUIConfig`, `updateUIConfig`, `listSaves`, `loadGame`, `saveGame` | 用户设置、存档会话 |
| `useModals` | `hooks/useModals.ts` | 间接：保存/加载服务 | 控制模态窗开闭与提交流程 |

## 约定
- Hooks 负责数据缓存与重试，避免组件重复请求。
- 若 Hook 新增 API 依赖，需在此表补充并更新相关模块文档。
- Hooks 返回的数据模型应与 `api.types.ts` 保持一致。

## TODO
- 为 `useGameState` 增加错误边界策略，并在此文档记录。
