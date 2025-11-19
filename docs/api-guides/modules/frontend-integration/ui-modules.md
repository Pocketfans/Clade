# UI 模块依赖

列出主要 UI 组件与其依赖的服务/Hook。

| 组件 | 文件 | 依赖 Hook/服务 | 相关端点 |
| --- | --- | --- | --- |
| MapCanvas | `frontend/src/map/MapCanvas.tsx` | `useGameState` (`fetchMapOverview`) | `/map` |
| ControlPanel | `frontend/src/components/ControlPanel.tsx` | `useGameState`, `usePressure` (`runTurn`, `addQueue`) | `/turns/run`, `/queue*` |
| HistoryPanel | `frontend/src/components/HistoryPanel.tsx` | `useGameState` (`fetchHistory`) | `/history` |
| SpeciesPanel | `frontend/src/components/SpeciesPanel/*` | `useSelection` (`fetchSpeciesDetail`, `fetchLineageTree`) | `/species/*`, `/lineage` |
| WatchlistPanel | `frontend/src/components/WatchlistPanel.tsx` | `useSelection`, `updateWatchlist` | `/watchlist` |
| SaveModal | `frontend/src/modals/SaveModal.tsx` | `useSession` (`listSaves`, `createSave`, `saveGame`, `loadGame`, `deleteSave`) | `/saves/*` |
| SettingsPanel | `frontend/src/ui/ConfigPanel.tsx` | `useSession` (`fetchUIConfig`, `updateUIConfig`, `testApiConnection`) | `/config/*` |

> 组件路径请在实现后校准，如文件名不同请更新本表。

## Mock 指南
- 可通过在 `services/api.ts` 中注入 `fetch = window.fetch` 替换机制来实现 Storybook/Fake API。
- 需要脱离后端时，可使用 `reports/sample/*.json` 作为数据源，记得注明数据日期。
