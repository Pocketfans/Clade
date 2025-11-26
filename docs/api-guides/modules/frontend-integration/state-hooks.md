# State Hooks 映射

描述 `frontend/src/hooks` 中各 Hook 如何消费服务层及 API。

| Hook | 文件 | 直接 API 依赖 | 说明 |
| --- | --- | --- | --- |
| `useGameState` | `hooks/useGameState.ts` | `fetchMapOverview`, `fetchLineageTree` | 负责地图缓存、族谱懒加载、错误状态；`reports` 目前由调用方（ControlPanel 等）注入 |
| `usePressure` | `hooks/usePressure.ts` | 无（仅本地状态） | 管理压力草稿数组，需与 `addQueue`/`runTurn` 手动组合 |
| `useSelection` | `hooks/useSelection.ts` | `fetchSpeciesDetail` | 选中地块/物种时拉取详情，并缓存最近一次结果 |
| `useSession` | `hooks/useSession.ts` | 无 | 仅负责本地 SessionStorage（scene/save 名称），不触发 API |
| `useModals` | `hooks/useModals.ts` | 无 | 纯 UI 状态，API 调用由模态组件自身完成 |

## 约定

- Hooks 负责缓存/节流，例如 `useGameState` 在同一次会话中只加载一次 `LineageTree`。
- 若未来在 Hook 中新增 API 调用，需在此表补充并更新模块文档。
- Hooks 返回的数据模型需与 `frontend/src/services/api.types.ts` 保持同步，避免类型漂移。

## TODO

- `useGameState`：计划增加 `runTurn` / `queue` 等接口的统一封装，并在此文档记录依赖。
