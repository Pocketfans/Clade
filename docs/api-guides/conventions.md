# API 统一规范

## 基础约定

- **Base Path**：所有端点均位于 `/api` 前缀下，由前端代理到 FastAPI。
- **版本**：当前为 `v1-beta`，破坏性变更需在 PR 描述与本文档中标注。
- **鉴权**：暂使用内置模拟身份，后续引入真实登录后补充。

## 请求/响应

- **Content-Type**：默认 `application/json`；文件导出保持当前实现。
- **错误结构**：
  ```json
  {
    "detail": "错误描述",
    "code": "可选的枚举",
    "hint": "可选的修复建议"
  }
  ```
- **分页**：若端点返回列表，参数命名统一为 `limit`（上限）与 `offset`，默认 limit=50。
- **过滤**：布尔参数使用 `true/false` 字符串。

## 命名与路径

- 名词使用复数：`/species`, `/saves`。
- 操作型子路径使用动词：`/queue/add`, `/queue/clear`。
- 子资源使用 `{identifier}` 占位：`/species/{lineage_code}`。

## 状态码

| 场景 | 状态码 | 说明 |
| --- | --- | --- |
| 成功 | 200/201 | 读取或创建成功 |
| 请求错误 | 400 | 校验失败、非法参数 |
| 未找到 | 404 | 资源不存在 |
| 服务器错误 | 500 | 未捕获异常（需在日志中附上下文） |

## 文档维护

- 新增端点 → 同步 `modules/<module>/README.md` 的接口表以及对应 Level 3 文件。
- 修改 Schema → 同步 `backend/app/schemas/*.py` + 前端 `api.types.ts` 并在文档中注明。
- 废弃端点 → 在模块 README 中标注“Deprecated”，并给出迁移策略。
