# UI 模块依赖

列出主要 UI 组件与其依赖的服务/Hook。

| 组件 | 文件 | 依赖 Hook/服务 | 相关端点 |
| --- | --- | --- | --- |
| MapCanvas / MapPanel | `frontend/src/components/MapCanvas.tsx`, `MapPanel.tsx` | `useGameState` (`fetchMapOverview`) | `/map` |
| ControlPanel | `frontend/src/components/ControlPanel.tsx` | `usePressure` + 直接调用 `runTurn`, `addQueue`, `clearQueue` | `/turns/run`, `/queue*` |
| HistoryTimeline / TurnReportPanel | `frontend/src/components/HistoryTimeline.tsx`, `TurnReportPanel.tsx` | 消费 `runTurn` 返回值或外部传入；无直接 API | `/turns/run`（间接） |
| SpeciesDetailPanel | `frontend/src/components/SpeciesDetailPanel.tsx` | `useSelection` (`fetchSpeciesDetail`), `useGameState` (`fetchLineageTree`) | `/species/{code}`, `/lineage` |
| SpeciesLedger | `frontend/src/components/SpeciesLedger.tsx` | 直接调用 `fetchSpeciesList`（通过 props 注入） | `/species/list` |
| SettingsDrawer | `frontend/src/components/SettingsDrawer.tsx` | `fetchUIConfig`, `updateUIConfig`, `testApiConnection` | `/config/ui`, `/config/test-api` |
| SaveModal / MainMenu | `frontend/src/components/CreateSpeciesModal.tsx`, `MainMenu.tsx` | `listSaves`, `createSave`, `saveGame`, `loadGame`, `deleteSave`, `generateSpecies` | `/saves/*`, `/species/generate` |
| AdminPanel | `frontend/src/components/AdminPanel.tsx` | `checkHealth`, `resetWorld` | `/admin/*` |
| NicheCompareView | `frontend/src/components/NicheCompareView.tsx` | `compareNiche` | `/niche/compare` |

> 组件命名/路径以 `frontend/src/components` 现状为准，如有调整请同步此表。

> 组件路径请在实现后校准，如文件名不同请更新本表。

## Mock 指南
- 可通过在 `services/api.ts` 中注入 `fetch = window.fetch` 替换机制来实现 Storybook/Fake API。
- 需要脱离后端时，可使用 `reports/sample/*.json` 作为数据源，记得注明数据日期。
