# 前端重构计划

## 📊 当前状态分析 (更新于 2025-12-02)

### 1. ✅ 已完成

| 任务 | 状态 | 说明 |
|------|------|------|
| ESLint + Prettier | ✅ | `eslint.config.mjs`, `.prettierrc` 已配置 |
| 路径别名 `@/` | ✅ | `tsconfig.json`, `vite.config.ts`, `vitest.config.ts` 已配置 |
| API 统一到 `@/services/api` | ✅ | 所有组件已迁移到别名导入，旧 `api.ts` 改为转发 |
| React Query 接入 | ✅ | `QueryProvider.tsx` + 示例 hooks 已创建 |
| 设计令牌 | ✅ | `styles/tokens.css` 已创建 |

### 2. 🔄 进行中

| 任务 | 状态 | 说明 |
|------|------|------|
| 组件拆分骨架 | 🔄 | `SpeciesPanel/`, `GenealogyGraphView/` 目录已建立，但主文件未替换 |
| CSS Modules | 🔄 | 部分组件有 `.module.css` 但未使用 |

### 3. 📋 待完成

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 运行 lint/test | P0 | 安装依赖后运行检查 |
| 落地组件拆分 | P1 | 用新结构替换旧大文件 |
| CSS Modules 落地 | P2 | FoodWebGraphNew.tsx 使用模块化样式 |
| 清理未用代码 | P3 | 删除旧 `api.ts`，清理全局样式 |

---

## 🔧 下一步操作

### 立即执行

```bash
# 1. 安装依赖
cd frontend
npm install

# 2. 运行 lint 检查
npm run lint

# 3. 运行测试
npm test
```

### API 迁移检查清单 ✅ 全部完成

- [x] `AIEnhancedTimeline.tsx` - 已迁移到 `@/services/api`
- [x] `AdminPanel.tsx` - 已迁移
- [x] `CreateSpeciesModal.tsx` - 已迁移
- [x] `EnhancedCreateSpeciesModal.tsx` - 已迁移
- [x] `GameSettingsMenu.tsx` - 已迁移
- [x] `GenealogyView.tsx` - 已迁移
- [x] `LogPanel.tsx` - 已迁移
- [x] `MainMenu.tsx` - 已迁移
- [x] `MapHistoryView.tsx` - 已迁移
- [x] `NicheCompareView.tsx` - 已迁移
- [x] `SettingsDrawer/sections/ConnectionSection.tsx` - 已迁移
- [x] `SpeciesPanel.tsx` - 已迁移
- [x] `TurnProgressOverlay.tsx` - 已迁移
- [x] `providers/GameProvider.tsx` - 已迁移
- [x] `providers/SessionProvider.tsx` - 已迁移
- [x] `providers/types.ts` - 已迁移
- [x] `App.tsx` - 已迁移
- [x] `hooks/*.ts` - 已迁移
- [x] `queries/*.ts` - 已迁移
- [x] 所有子组件目录 - 已迁移

---

## 📁 新增文件

```
frontend/
├── eslint.config.mjs              # ESLint 配置
├── .prettierrc                    # Prettier 配置
├── .prettierignore                # Prettier 忽略
├── src/
│   ├── providers/
│   │   └── QueryProvider.tsx      # React Query 配置
│   ├── queries/
│   │   ├── useSpeciesQuery.ts     # 物种查询 hooks
│   │   └── useFoodWebQuery.ts     # 食物网查询 hooks
│   ├── services/
│   │   └── api.ts                 # 已改为转发层 (deprecated)
│   └── styles/
│       └── tokens.css             # 设计令牌
```

---

## 📦 package.json 变更

### 新增依赖
```json
{
  "dependencies": {
    "@tanstack/react-query": "^5.62.3"
  },
  "devDependencies": {
    "@eslint/js": "^9.15.0",
    "eslint": "^9.15.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.14",
    "prettier": "^3.4.2",
    "typescript-eslint": "^8.16.0"
  }
}
```

### 新增脚本
```json
{
  "scripts": {
    "lint": "eslint src",
    "lint:fix": "eslint src --fix",
    "format": "prettier --write src",
    "format:check": "prettier --check src"
  }
}
```

---

## 🏗️ 组件拆分进度

### SpeciesPanel/ ✅ 骨架已建立

```
SpeciesPanel/
├── index.ts                       ✅ 导出
├── components/
│   ├── SpeciesListHeader.tsx      ✅ 完整实现
│   └── SpeciesListItem.tsx        ✅ 完整实现
├── hooks/
│   ├── useSpeciesList.ts          ✅ 完整实现
│   ├── useSpeciesDetail.ts        ✅ 完整实现
│   └── useSpeciesFilter.ts        ✅ 完整实现
├── types.ts                       ✅ 完整
├── constants.ts                   ✅ 完整
└── utils.ts                       ✅ 完整
```

**待完成**: 创建新的主组件 `SpeciesPanelNew.tsx`，替换 `../SpeciesPanel.tsx`

### GenealogyGraphView/ ✅ 骨架已建立

```
GenealogyGraphView/
├── index.ts                       ✅ 导出
├── hooks/
│   ├── useCamera.ts               ✅ 完整实现
│   └── useCollapse.ts             ✅ 完整实现
├── utils/
│   └── layout.ts                  ✅ 完整实现
├── types.ts                       ✅ 完整
└── constants.ts                   ✅ 完整
```

**待完成**: 创建新的主组件 `GenealogyGraphViewNew.tsx`，替换 `../GenealogyGraphView.tsx`

---

## 🧪 React Query 使用示例

### 获取物种列表
```tsx
import { useSpeciesListQuery } from "@/queries";

function SpeciesList() {
  const { data, isLoading, error, refetch } = useSpeciesListQuery();
  
  if (isLoading) return <Loading />;
  if (error) return <Error message={error.message} />;
  
  return (
    <ul>
      {data?.map(species => (
        <li key={species.lineage_code}>{species.common_name}</li>
      ))}
    </ul>
  );
}
```

### 获取物种详情
```tsx
import { useSpeciesDetailQuery } from "@/queries";

function SpeciesDetail({ code }: { code: string }) {
  const { data, isLoading } = useSpeciesDetailQuery(code);
  // ...
}
```

### 修改物种
```tsx
import { useEditSpeciesMutation } from "@/queries";

function EditSpecies() {
  const mutation = useEditSpeciesMutation();
  
  const handleSave = async () => {
    await mutation.mutateAsync({
      lineageCode: "A1",
      data: { description: "Updated description" }
    });
  };
  // ...
}
```

---

## 📚 参考资料

- [React Query 文档](https://tanstack.com/query/latest)
- [ESLint Flat Config](https://eslint.org/docs/latest/use/configure/configuration-files-new)
- [CSS Modules](https://github.com/css-modules/css-modules)
- [Testing Library 最佳实践](https://testing-library.com/docs/queries/about)
