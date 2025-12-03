# API 迁移指南

本指南说明如何将组件从旧版 `services/api.ts` 迁移到新版模块化 API `services/api/`。

## 快速迁移

### 1. 更新导入语句

```tsx
// 旧版 ❌
import { runTurn, fetchMapOverview, fetchSpeciesList } from "../services/api";

// 新版 ✅ (推荐使用路径别名)
import { runTurn, fetchMapOverview, fetchSpeciesList } from "@/services/api";

// 或相对路径
import { runTurn, fetchMapOverview, fetchSpeciesList } from "../services/api";
```

### 2. 类型导入

```tsx
// 旧版 ❌
import type { TurnReport, SpeciesDetail } from "../services/api.types";

// 新版 ✅
import type { TurnReport, SpeciesDetail } from "@/services/api.types";
// 或从具体模块导入
import type { GameState } from "@/services/api/saves";
import type { ApiError } from "@/services/api/base";
```

## API 对照表

| 旧版函数 | 新版函数 | 模块 |
|---------|---------|------|
| `runTurn` | `runTurn` | `turns` |
| `runBatchTurns` | `runBatchTurns` | `turns` |
| `fetchHistory` | `fetchHistory` | `turns` |
| `fetchQueueStatus` | `fetchQueueStatus` | `turns` |
| `addQueue` | `addQueue` | `turns` |
| `clearQueue` | `clearQueue` | `turns` |
| `fetchPressureTemplates` | `fetchPressureTemplates` | `turns` |
| `fetchMapOverview` | `fetchMapOverview` | `map` |
| `fetchHeightMap` | `fetchHeightMap` | `map` |
| `fetchWaterMask` | `fetchWaterMask` | `map` |
| `fetchErosionMap` | `fetchErosionMap` | `map` |
| `fetchSpeciesList` | `fetchSpeciesList` | `species` |
| `fetchSpeciesDetail` | `fetchSpeciesDetail` | `species` |
| `editSpecies` | `editSpecies` | `species` |
| `generateSpecies` | `generateSpecies` | `species` |
| `generateSpeciesAdvanced` | `generateSpeciesAdvanced` | `species` |
| `compareNiche` | `compareNiche` | `species` |
| `fetchLineageTree` | `fetchLineageTree` | `species` |
| `invalidateLineageCache` | `invalidateLineageCache` | `species` |
| `updateWatchlist` | `updateWatchlist` | `species` |
| `fetchUIConfig` | `fetchUIConfig` | `config` |
| `updateUIConfig` | `updateUIConfig` | `config` |
| `testApiConnection` | `testApiConnection` | `config` |
| `fetchProviderModels` | `fetchProviderModels` | `config` |
| `fetchGameState` | `fetchGameState` | `saves` |
| `listSaves` | `listSaves` | `saves` |
| `createSave` | `createSave` | `saves` |
| `saveGame` | `saveGame` | `saves` |
| `loadGame` | `loadGame` | `saves` |
| `deleteSave` | `deleteSave` | `saves` |
| `fetchFoodWeb` | `fetchFoodWeb` | `ecosystem` |
| `fetchSpeciesFoodChain` | `fetchSpeciesFoodChain` | `ecosystem` |
| `analyzeExtinctionImpact` | `analyzeExtinctionImpact` | `ecosystem` |
| `fetchFoodWebAnalysis` | `fetchFoodWebAnalysis` | `ecosystem` |
| `repairFoodWeb` | `repairFoodWeb` | `ecosystem` |
| `checkHealth` | `checkHealth` | `admin` |
| `resetWorld` | `resetWorld` | `admin` |
| `dropDatabase` | `dropDatabase` | `admin` |
| `fetchLogs` | `fetchLogs` | `admin` |
| `fetchAIDiagnostics` | `fetchAIDiagnostics` | `admin` |
| `resetAIDiagnostics` | `resetAIDiagnostics` | `admin` |
| `abortCurrentTasks` | `abortCurrentTasks` | `admin` |
| `skipCurrentAIStep` | `skipCurrentAIStep` | `admin` |
| `getTaskDiagnostics` | `getTaskDiagnostics` | `admin` |
| `connectToEventStream` | `connectToEventStream` | `events` |

## 错误处理

新版 API 提供统一的错误类型：

```tsx
import type { ApiError } from "@/services/api";

try {
  const data = await fetchSpeciesList();
} catch (error) {
  if ((error as ApiError).status === 404) {
    // 处理 404
  } else if ((error as ApiError).status === 0) {
    // 请求超时或网络错误
  }
}
```

## 请求配置

新版 API 支持统一的请求配置：

```tsx
import { http } from "@/services/api";

// 自定义超时
const data = await http.get("/api/species", { timeout: 60000 });

// 取消请求
const controller = new AbortController();
const data = await http.get("/api/species", { signal: controller.signal });
controller.abort();
```

## 迁移检查清单

迁移组件时，检查以下事项：

- [ ] 更新导入路径
- [ ] 更新类型导入
- [ ] 测试 API 调用正常工作
- [ ] 检查错误处理是否仍然有效
- [ ] 移除未使用的旧版导入

## 待迁移文件列表

以下文件仍在使用旧版 API：

1. `AIAssistantPanel.tsx`
2. `AdminPanel.tsx`
3. `CreateSpeciesModal.tsx`
4. `EnhancedCreateSpeciesModal.tsx`
5. `GameSettingsMenu.tsx`
6. `GenealogyView.tsx`
7. `LogPanel.tsx`
8. `MainMenu.tsx`
9. `MapHistoryView.tsx`
10. `NicheCompareView.tsx`
11. `SettingsDrawer/sections/ConnectionSection.tsx`
12. `SpeciesAITab.tsx`
13. `SpeciesPanel.tsx`
14. `TurnProgressOverlay.tsx`
15. `SpeciesPanel/hooks/useSpeciesDetail.ts`
16. `FoodWebGraph/hooks/useFoodWebData.ts`
17. `SettingsDrawer/types.ts`
18. `AIEnhancedTimeline.tsx`




