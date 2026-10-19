# 接口契约（API Contract）

> 项目：智能学习系统 ｜ 版本：v1 ｜ 更新：2026-10-18
> 本文档是**前后端联调与代码生成的唯一依据**。任何字段变更必须先改本文档，再改代码。

---

## 1. 全局约定

### 1.1 基础信息

| 项 | 约定 |
|---|---|
| Base URL | `http://localhost:8000` |
| 业务前缀 | `/api/v1`（健康检查除外） |
| 传输 | JSON（`Content-Type: application/json`），文件上传为 `multipart/form-data` |
| 字段命名 | **全链路 snake_case**，不做 camelCase 转换 |
| 认证 | `Authorization: Bearer <access_token>` |
| 时间 | ISO 8601 UTC，如 `2026-10-18T03:20:11Z`；日期字段为 `YYYY-MM-DD` |
| 主键 | UUID 字符串（36 位带连字符） |
| 文档 | `/docs`（Swagger UI）、`/openapi.json` |

### 1.2 分页

请求：`?page=1&size=20`（`page` 从 1 开始，`size` 默认 20、上限 100）

响应（**所有列表接口统一此结构**）：

```json
{ "items": [], "total": 0, "page": 1, "size": 20 }
```

### 1.3 错误响应

```json
{
  "code": "MAT_003",
  "message": "文件类型不支持，仅接受 PDF 与 DOCX",
  "detail": { "field": "file", "received_ext": ".doc" }
}
```

- `message` 是**可直接展示给用户的中文文案**，前端统一 toast 即可，不要自己拼文案。
- `detail` 可为 `null`、对象或数组；`422` 时是 Pydantic 的 `errors` 数组。

> **Swagger 里的 422 已与本契约对齐**：FastAPI 默认会把 422 渲染成 `{"detail": [...]}`，
> 我们在 `main.py` 用 `include_router(responses={422: {"model": ErrorOut}})`
> 覆盖成 `{code, message, detail}`。新增路由时不要自己再声明 422，否则会重复定义。

### 1.4 错误码表

| HTTP | code | 含义 |
|---|---|---|
| 400 | `SYS_400` | 参数语义错误（如日期区间颠倒、分页越界） |
| 401 | `AUTH_001` | 未提供凭证 |
| 401 | `AUTH_002` | access token 已过期 → 前端触发刷新 |
| 401 | `AUTH_003` | 凭证无效或已被吊销 |
| 403 | `AUTH_004` | 权限不足（该接口需要管理员角色） |
| 403 | `USER_003` | 账号已被禁用（展示 `disabled_reason`） |
| 400 | `ADMIN_001` | 管理员不能对自己执行该操作（禁用 / 降级 / 重置密码 / 强制下线） |
| 403 | `AUTH_005` | 请求来源不被允许（CSRF 防护：refresh/logout 的 `Origin` 校验失败） |
| 400 | `USER_004` | 原密码不正确 |
| 404 | `SYS_404` | 资源不存在**或不属于当前用户**（故意不区分，防 ID 枚举） |
| 409 | `USER_001` | 用户名已存在 |
| 409 | `USER_002` | 邮箱已存在 |
| 409 | `PLAN_001` | 该日期区间的任务已生成过（幂等冲突） |
| 413 | `MAT_002` | 文件超过 `MAX_UPLOAD_MB` |
| 422 | `SYS_422` | 请求体校验失败（detail 为字段级错误） |
| 429 | `AI_004` | 超出当日 AI 调用配额 |
| 500 | `SYS_500` | 服务内部错误 |
| 502 | `AI_002` | 上游模型返回异常 |
| 503 | `SYS_503` | 功能已被管理员关闭（如 `ai.enabled=false`、`register.allow=false`） |
| 504 | `AI_003` | AI 调用超时（含 agent 循环总时长超时） |
| — | `MAT_001` | 解析失败（随 200 状态在 `parse_status` 中体现，也可用于解析接口） |
| — | `MAT_003` | 文件类型不支持 |
| — | `MAT_004` | 扫描版 PDF，暂不支持 OCR |
| — | `AI_001` | AI 输出结构校验失败且重试后仍失败 |
| — | `AI_005` | 问题过于复杂，超出 agent 步数上限 |

> 约定：**用户端的越权一律返回 404**，不能返回 403（否则可通过状态码枚举出「别人的资源存在」）。
> 403 只用于两种情况：① 登录用户访问管理端接口但角色不足（`AUTH_004`）；② 账号被管理员禁用（`USER_003`）。
> 404 与 403 的边界是「**资源是否存在**」与「**你有没有资格进这个门**」，不要混用。

### 1.5 认证与 Cookie

| 项 | 值 |
|---|---|
| access token | JWT，`exp` 30 分钟，**前端存内存**（Zustand），不进 localStorage |
| refresh token | JWT，7 天，`Set-Cookie: sl_refresh=...`；`HttpOnly` + `SameSite=Lax` + `Secure`(生产) + `Path=/api/v1/auth` |
| 刷新逻辑 | 401 且 `code=AUTH_002` → 调 `/auth/refresh` → 重放原请求；并发请求共享同一个刷新 Promise |
| CSRF | `/auth/refresh`、`/auth/logout` 为 Cookie 凭证接口，服务端校验 `Origin` 头 |

> **角色与账号状态的判定**：JWT 只携带 `sub`（用户 ID）、`pv`（`token_version`）、`exp`。
> 每次鉴权都按 `sub` 读库取 `role` 与 `is_active` —— **不信任 token 里的任何角色声明**（否则一旦 token 泄露就无法降权）。
> 因此「改角色 / 禁用账号 / 强制下线」只需把 `token_version` +1，旧 token 立刻全部失效，无需额外机制。
> 登录时若 `is_active=false` → 403 `USER_003`，`message` 为 `账号已被禁用：<disabled_reason>`。

### 1.6 其他约定

- 写操作的幂等性：`POST /plans/{id}/generate-tasks` 幂等（靠唯一索引 `(plan_id, plan_date)`）；其余 `POST` 非幂等。
- 软删除：删除接口返回 `204`，数据仅置 `deleted_at`；后续查询永久不可见。
- 长文本不外传：`material.extracted_text` 不出现在任何列表/详情响应中，改用 `/materials/{id}/text` 分片读取。
- 健康检查：`GET /health`（不带版本前缀，供 Docker healthcheck 使用）。

---

## 2. 端点总览

| # | 功能 | Method | Path | 认证 |
|---|---|---|---|---|
| 1 | 健康检查 | GET | `/health` | 否 |
| 1 | 注册 | POST | `/api/v1/auth/register` | 否 |
| 1 | 登录 | POST | `/api/v1/auth/login` | 否 |
| 1 | 刷新令牌 | POST | `/api/v1/auth/refresh` | Cookie |
| 1 | 登出 | POST | `/api/v1/auth/logout` | Cookie |
| 2 | 我的信息 | GET | `/api/v1/users/me` | 是 |
| 2 | 修改我的信息 | PATCH | `/api/v1/users/me` | 是 |
| 2 | 修改密码 | POST | `/api/v1/users/me/password` | 是 |
| 2 | 上传头像 | POST | `/api/v1/users/me/avatar` | 是 |
| 3 | 上传资料 | POST | `/api/v1/materials` | 是 |
| 3 | 资料列表 | GET | `/api/v1/materials` | 是 |
| 3 | 资料详情 | GET | `/api/v1/materials/{id}` | 是 |
| 3 | 修改资料 | PATCH | `/api/v1/materials/{id}` | 是 |
| 3 | 删除资料 | DELETE | `/api/v1/materials/{id}` | 是 |
| 3 | 下载原文件 | GET | `/api/v1/materials/{id}/download` | 是 |
| 3 | 分片读正文 | GET | `/api/v1/materials/{id}/text` | 是 |
| 3 | 重新解析 | POST | `/api/v1/materials/{id}/reparse` | 是 |
| 4 | 新建笔记 | POST | `/api/v1/notes` | 是 |
| 4 | 笔记列表 | GET | `/api/v1/notes` | 是 |
| 4 | 笔记详情 | GET | `/api/v1/notes/{id}` | 是 |
| 4 | 修改笔记 | PATCH | `/api/v1/notes/{id}` | 是 |
| 4 | 删除笔记 | DELETE | `/api/v1/notes/{id}` | 是 |
| 5 | 新建计划 | POST | `/api/v1/plans` | 是 |
| 5 | 计划列表 | GET | `/api/v1/plans` | 是 |
| 5 | 计划详情 | GET | `/api/v1/plans/{id}` | 是 |
| 5 | 修改计划 | PATCH | `/api/v1/plans/{id}` | 是 |
| 5 | 删除计划 | DELETE | `/api/v1/plans/{id}` | 是 |
| 6 | 生成每日任务 | POST | `/api/v1/plans/{id}/generate-tasks` | 是 |
| 6 | 任务列表 | GET | `/api/v1/tasks` | 是 |
| 6 | 手工建任务 | POST | `/api/v1/tasks` | 是 |
| 6 | 修改任务 | PATCH | `/api/v1/tasks/{id}` | 是 |
| 6 | 完成任务（同时记学习记录） | POST | `/api/v1/tasks/{id}/complete` | 是 |
| 6 | 删除任务 | DELETE | `/api/v1/tasks/{id}` | 是 |
| 12 | 新建学习记录 | POST | `/api/v1/study-records` | 是 |
| 12 | 学习记录列表 | GET | `/api/v1/study-records` | 是 |
| 12 | 修改学习记录 | PATCH | `/api/v1/study-records/{id}` | 是 |
| 12 | 删除学习记录 | DELETE | `/api/v1/study-records/{id}` | 是 |
| 7 | 新建会话 | POST | `/api/v1/ai/chat-sessions` | 是 |
| 7 | 会话列表 | GET | `/api/v1/ai/chat-sessions` | 是 |
| 7 | 会话历史消息 | GET | `/api/v1/ai/chat-sessions/{id}/messages` | 是 |
| 7 | 删除会话 | DELETE | `/api/v1/ai/chat-sessions/{id}` | 是 |
| 7 | 提问（流式） | POST | `/api/v1/ai/chat-sessions/{id}/messages/stream` | 是 |
| 7 | 提问（非流式） | POST | `/api/v1/ai/chat-sessions/{id}/messages` | 是 |
| 8 | 生成资料总结 | POST | `/api/v1/ai/summaries` | 是 |
| 8 | 资料总结列表 | GET | `/api/v1/ai/summaries` | 是 |
| 8 | 资料总结详情 | GET | `/api/v1/ai/summaries/{id}` | 是 |
| 9 | 生成测试题 | POST | `/api/v1/ai/quizzes` | 是 |
| 9 | 测试题列表 | GET | `/api/v1/quizzes` | 是 |
| 9 | 测试题详情 | GET | `/api/v1/quizzes/{id}` | 是 |
| 9 | 删除测试题 | DELETE | `/api/v1/quizzes/{id}` | 是 |
| 9 | 提交答卷 | POST | `/api/v1/quizzes/{id}/attempts` | 是 |
| 9 | 答卷记录 | GET | `/api/v1/quizzes/{id}/attempts` | 是 |
| 9 | 答卷详情 | GET | `/api/v1/attempts/{id}` | 是 |
| 10 | 生成学习建议 | POST | `/api/v1/ai/advice/generate` | 是 |
| 10 | 最新学习建议 | GET | `/api/v1/ai/advice` | 是 |
| 10 | 建议历史 | GET | `/api/v1/ai/advice/history` | 是 |
| 11 | 总览统计 | GET | `/api/v1/stats/overview` | 是 |
| 11 | 每日趋势 | GET | `/api/v1/stats/daily` | 是 |
| 11 | 科目分布 | GET | `/api/v1/stats/subjects` | 是 |
| 11 | 薄弱知识点 | GET | `/api/v1/stats/weak-points` | 是 |
| — | AI 用量 | GET | `/api/v1/ai/usage` | 是 |

**功能 13：管理员端**（全部需要 `role=admin`；路径前缀 `/api/v1/admin`）

| # | 子模块 | Method | Path |
|---|---|---|---|
| 13.1 | 仪表盘总览 | GET | `/api/v1/admin/stats/overview` |
| 13.1 | 全站每日趋势 | GET | `/api/v1/admin/stats/daily` |
| 13.1 | AI 用量统计 | GET | `/api/v1/admin/stats/ai` |
| 13.2 | 用户列表 | GET | `/api/v1/admin/users` |
| 13.2 | 用户详情 | GET | `/api/v1/admin/users/{id}` |
| 13.2 | 修改用户（启用/禁用/角色） | PATCH | `/api/v1/admin/users/{id}` |
| 13.2 | 重置用户密码 | POST | `/api/v1/admin/users/{id}/reset-password` |
| 13.2 | 强制用户下线 | POST | `/api/v1/admin/users/{id}/revoke-tokens` |
| 13.3 | 全站资料列表 | GET | `/api/v1/admin/materials` |
| 13.3 | 下架资料 | DELETE | `/api/v1/admin/materials/{id}` |
| 13.3 | 重新解析资料 | POST | `/api/v1/admin/materials/{id}/reparse` |
| 13.3 | 全站笔记列表 | GET | `/api/v1/admin/notes` |
| 13.3 | 删除笔记 | DELETE | `/api/v1/admin/notes/{id}` |
| 13.3 | 全站测试题列表 | GET | `/api/v1/admin/quizzes` |
| 13.3 | 删除测试题 | DELETE | `/api/v1/admin/quizzes/{id}` |
| 13.4 | AI 调用明细 | GET | `/api/v1/admin/ai-usage` |
| 13.5 | 读取系统配置 | GET | `/api/v1/admin/settings` |
| 13.5 | 修改系统配置 | PATCH | `/api/v1/admin/settings` |
| 13.5 | 操作审计日志 | GET | `/api/v1/admin/audit-logs` |

---

## 3. 认证 `/auth`

### POST `/api/v1/auth/register`

```json
// 请求
{ "username": "zhangsan", "email": "z@example.com", "password": "Passw0rd!", "nickname": "张三" }
```

约束：`username` 3-32 位字母数字下划线；`email` 合法邮箱；`password` ≥8 位且含字母与数字；`nickname` 1-32 位可选。

> **邮箱校验口径（有意为之）**：使用 Pydantic `EmailStr` 的**默认宽松策略** —— 不做 DNS 可达性检查，且允许国际化域名（IDN）。
> 代价是 `a@不存在的域名.com` 这类输入会被接受。本项目注册流程不发验证邮件，因此选择宽松以减少对离线环境/测试的依赖。
> 若将来需要严格校验（例如发送激活邮件），应改为 `check_deliverability=True` 或限制为 ASCII 域名 —— 这属于契约变更，需先改本节。

```json
// 201
{ "id": "…", "username": "zhangsan", "email": "z@example.com", "nickname": "张三", "created_at": "2026-10-18T03:20:11Z" }
```

> 注册**不自动登录**，前端注册成功后调用 `/auth/login`。
> 与上一条无关的注意点：响应中**永不出现** `password_hash`。

### POST `/api/v1/auth/login`

`Content-Type: application/x-www-form-urlencoded`（OAuth2 规范，字段名固定为 `username` / `password`，Swagger 的 Authorize 按钮可直连）

```json
// 200
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 1800, "role": "user" }
// 响应头：Set-Cookie: sl_refresh=…; HttpOnly; SameSite=Lax; Path=/api/v1/auth
```

`role` 仅用于前端决定是否显示「管理端」入口，**服务端鉴权不依赖它**。

失败：401 `AUTH_003`，`message` 固定为 `用户名或密码错误`（不区分账号是否存在）。

### POST `/api/v1/auth/refresh`

无请求体，仅依赖 Cookie。成功返回新的 `access_token` 并**轮换** refresh Cookie。失败 401 `AUTH_003`（前端跳登录页）。

### POST `/api/v1/auth/logout`

`204`，清除 Cookie。已过期的 refresh token 也返回 204（幂等）。

---

## 4. 用户 `/users`

### GET `/api/v1/users/me`

```json
{
  "id": "…", "username": "zhangsan", "email": "z@example.com", "nickname": "张三",
  "avatar_url": null, "learning_goal": "通过期末考试", "daily_target_minutes": 60,
  "role": "user", "created_at": "2026-10-18T03:20:11Z"
}
```

### PATCH `/api/v1/users/me`

可改字段：`email`、`nickname`、`avatar_url`、`learning_goal`（≤200 字）、`daily_target_minutes`（1-1440）。
邮箱冲突 → 409 `USER_002`。

### POST `/api/v1/users/me/password`

```json
{ "old_password": "Passw0rd!", "new_password": "NewPassw0rd!" }
```

成功 `204`，并**吊销该用户全部 refresh token**（强制其他设备重新登录）。

### POST `/api/v1/users/me/avatar`

`multipart/form-data`，字段 `file`。仅 `.png/.jpg/.jpeg`，≤2MB。返回 `200 {"avatar_url": "/api/v1/files/avatars/xxx.jpg"}`。

---

## 5. 学习资料 `/materials`

### POST `/api/v1/materials`

`multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | `.pdf` / `.docx`，≤20MB |
| `title` | string | 否 | 缺省取文件名（去扩展名） |
| `subject` | string | 否 | 科目，用于统计与推荐 |
| `tags` | string | 否 | 逗号分隔，如 `高数,极限` |

```json
// 202 Accepted（解析在后台进行）
{
  "id": "…", "title": "高等数学 第一章", "subject": "高数", "tags": ["高数", "极限"],
  "file_name": "chapter1.pdf", "file_ext": ".pdf", "mime_type": "application/pdf",
  "size_bytes": 2048576, "page_count": null, "char_count": null,
  "parse_status": "pending", "parse_error": null, "created_at": "2026-10-18T03:20:11Z"
}
```

`parse_status` 取值与含义：

| 值 | 含义 | 前端表现 |
|---|---|---|
| `pending` | 排队中 | 转圈，轮询详情 |
| `parsing` | 解析中 | 转圈 |
| `success` | 成功 | 可总结 / 出题 / 问答 |
| `failed` | 解析失败 | 显示「重试解析」按钮 |
| `unsupported` | 扫描版 PDF，无文本层 | 提示「暂不支持 OCR」（`MAT_004`） |

> 前端：上传后每 2s 轮询一次详情，最多 30 次；拿到 `success/failed/unsupported` 即停。

**上传失败的响应（对应 §1.4 的错误码）**

| HTTP | code | 触发条件 |
|---|---|---|
| 413 | `MAT_002` | 文件超过 `MAX_UPLOAD_MB`（默认 20MB） |
| 400 | `MAT_003` | 扩展名不在白名单 / MIME 明显不符 / **文件头魔数与扩展名不符**（防伪装文件） |

> 扫描版 PDF **不是错误**：仍返回 `202`，只是 `parse_status=unsupported` + `parse_error` 里说明「暂不支持 OCR」。
> 这样前端可以统一按状态机渲染，不需要把「业务可预期的情况」混进异常分支。

### GET `/api/v1/materials`

Query：`page`、`size`、`keyword`（匹配 title）、`subject`、`parse_status`、`order`（`-created_at` 默认）
响应 item 同上传返回结构（**不含** `extracted_text`）。

### GET `/api/v1/materials/{id}`

同上，item 为单对象。

### PATCH `/api/v1/materials/{id}`

可改：`title`、`subject`、`tags`。

### DELETE `/api/v1/materials/{id}`

`204`。软删除；同时删除磁盘文件（失败不阻断，记 warning 日志）。
若有未完成的计划任务引用该资料，仍允许删除，任务保留但 `material_id` 置空。

### GET `/api/v1/materials/{id}/download`

返回 `FileResponse`，`Content-Disposition: attachment; filename*=UTF-8''<原名>`。
**必须**校验归属后再返回文件，绝不能暴露静态目录。

### GET `/api/v1/materials/{id}/text`

Query：`offset`（默认 0）、`limit`（默认 4000，上限 8000）

```json
{
  "material_id": "…", "offset": 0, "limit": 4000,
  "total_chars": 38210, "has_more": true,
  "text": "…（正文片段）"
}
```

> 此接口与 agent 工具 `read_material_chunk` **复用同一个 service 函数**，保证行为一致。

### POST `/api/v1/materials/{id}/reparse`

`202`，重置 `parse_status=pending` 并重新解析。仅允许在 `failed` / `unsupported` 状态调用，其他状态返回 400 `SYS_400`。

---

## 6. 笔记 `/notes`

### POST `/api/v1/notes`

```json
{ "title": "极限的两种定义", "content": "…markdown…", "tags": ["高数"], "material_id": null }
```

约束：`title` 1-200 字；`content` ≤100000 字；`material_id` 若提供必须属于当前用户（否则 404）。

### GET `/api/v1/notes`

Query：`page`、`size`、`keyword`（在 title 与 content 上做 `ILIKE` + `pg_trgm` 索引）、`material_id`、`tag`、`order`。
列表 item **不含** `content`，只返回 `excerpt`（前 120 字）——避免列表接口返回大字段。

```json
{ "items": [{ "id": "…", "title": "…", "excerpt": "…", "tags": [], "material_id": null, "updated_at": "…" }], "total": 1, "page": 1, "size": 20 }
```

### GET / PATCH / DELETE `/api/v1/notes/{id}`

详情返回含 `content` 的完整对象；PATCH 可改 `title`、`content`、`tags`、`material_id`；DELETE 返回 `204`。

---

## 7. 学习计划 `/plans`

### POST `/api/v1/plans`

```json
{
  "title": "高数期末冲刺", "subject": "高数", "goal": "期末 85+",
  "start_date": "2026-10-20", "end_date": "2026-11-20",
  "daily_minutes": 60, "material_ids": ["…", "…"]
}
```

约束：`end_date ≥ start_date`；区间 ≤180 天；`daily_minutes` 1-600。

```json
// 201
{ "id": "…", "title": "高数期末冲刺", "subject": "高数", "goal": "期末 85+",
  "start_date": "2026-10-20", "end_date": "2026-11-20", "daily_minutes": 60,
  "status": "active", "material_ids": ["…"], "created_at": "…" }
```

`status`：`draft` / `active` / `done` / `archived`。

### GET `/api/v1/plans`

Query：`page`、`size`、`status`。
item 额外含进度概要：`{ "task_total": 32, "task_done": 12, "progress": 0.375 }`。

### GET `/api/v1/plans/{id}`

含进度概要 + 引用资料列表（只返回 `id`/`title`/`subject`）。

### PATCH `/api/v1/plans/{id}`

可改 `title`、`goal`、`daily_minutes`、`status`、`material_ids`。
**`start_date`/`end_date` 不可改**（已生成的任务会与区间不一致），需要改区间就新建计划 → 返回 400 `SYS_400`。

### DELETE `/api/v1/plans/{id}`

`204`，级联软删除未完成任务（已完成任务保留，用于统计）。

---

## 8. 学习任务 `/tasks`

### POST `/api/v1/plans/{id}/generate-tasks`

```json
// 请求（可空，使用默认）
{ "overwrite": false }
```

```json
// 201
{ "plan_id": "…", "created": 32, "skipped": 0, "dates": ["2026-10-20", "…"] }
```

规则：
- 按计划区间逐日生成，每个计划日一条主任务（`title` 取计划标题 + 当日序号），`order_no` 递增。
- 依赖唯一索引 `(plan_id, plan_date)` 保证幂等；已存在的日期计入 `skipped`，**不报错**。
- 若计划区间内**全部**已存在，返回 409 `PLAN_001`（提示「任务已生成」，避免用户重复点击）。
- `overwrite=true` 时删除该区间内 `status=pending` 的任务后重建（已 `done` 的不动）。

### GET `/api/v1/tasks`

Query：`page`、`size`、`plan_id`、`plan_date`（`YYYY-MM-DD`）、`date_from`、`date_to`、`status`。

```json
{ "items": [{ "id": "…", "plan_id": "…", "plan_date": "2026-10-20", "title": "高数期末冲刺 D1",
  "description": null, "order_no": 1, "est_minutes": 60, "status": "pending",
  "completed_at": null, "material_id": null }], "total": 1, "page": 1, "size": 20 }
```

### POST `/api/v1/tasks`

```json
{ "plan_id": null, "plan_date": "2026-10-20", "title": "复习英语单词", "description": null, "est_minutes": 30, "material_id": null }
```

### PATCH `/api/v1/tasks/{id}`

可改 `title`、`description`、`est_minutes`、`status`、`plan_date`、`material_id`。
`plan_date` 变更需满足 `(plan_id, plan_date)` 唯一约束，冲突返回 409 `PLAN_001`。

### POST `/api/v1/tasks/{id}/complete`

```json
// 请求
{ "duration_minutes": 55, "content": "看完第一章并做完例题", "create_record": true }
```

```json
// 200（原子操作：置任务 done + 写一条 study_record）
{ "task": { "id": "…", "status": "done", "completed_at": "2026-10-20T13:00:00Z" },
  "study_record_id": "…" }
```

`create_record=false` 时只改状态，`study_record_id` 为 `null`。

### DELETE `/api/v1/tasks/{id}`

`204`。

---

## 9. 学习记录 `/study-records`

### POST `/api/v1/study-records`

```json
{ "task_id": null, "material_id": null, "type": "reading",
  "started_at": "2026-10-20T12:00:00Z", "duration_minutes": 55, "content": "…" }
```

`type`：`reading` / `video` / `practice` / `review` / `other`；`duration_minutes` 1-1440；
`started_at` 不允许晚于当前时间 +5 分钟（防止乱填影响统计）。

### GET `/api/v1/study-records`

Query：`page`、`size`、`date_from`、`date_to`、`type`、`plan_id`（经任务关联过滤）。
默认 `order=-started_at`。

### PATCH / DELETE `/api/v1/study-records/{id}`

PATCH 可改 `type`、`duration_minutes`、`content`、`started_at`；DELETE `204`。

---

## 10. AI：问答 `/ai/chat-sessions`

### POST `/api/v1/ai/chat-sessions`

```json
{ "title": null, "material_id": "…" }
```

`material_id` 为 `null` 时表示「不限定资料」（agent 可用 `search_material` 全库检索）。
`title` 为空时先用占位标题，首轮回答完成后由后端截取问题前 20 字更新（**不额外调用模型**）。
返回 `201`：

```json
{ "id": "…", "title": "新会话", "material_id": "…", "message_count": 0, "last_message_at": null, "created_at": "…" }
```

### GET `/api/v1/ai/chat-sessions`

分页，item 同上。默认 `order=-last_message_at`（空值排最后）。

### GET `/api/v1/ai/chat-sessions/{id}/messages`

分页，`order=created_at`（升序）。

```json
{ "items": [{ "id": "…", "role": "assistant", "content": "…", "tool_calls": null,
  "prompt_tokens": 386, "completion_tokens": 26, "latency_ms": 3210, "created_at": "…" }], "total": 4, "page": 1, "size": 20 }
```

`role`：`user` / `assistant`。**`tool` 与 `system` 角色的中间消息不落库**，只在流式过程中作为事件推送（见 §13）。

### DELETE `/api/v1/ai/chat-sessions/{id}`

`204`，级联软删除消息。

### POST `/api/v1/ai/chat-sessions/{id}/messages/stream` ★

请求：

```json
{ "content": "第一章的极限定义是什么？", "material_id": "…" }
```

响应：`Content-Type: text/event-stream`，SSE 事件协议见 **§13**。

### POST `/api/v1/ai/chat-sessions/{id}/messages`

非流式版本（供前端降级开关与自动化测试使用）。请求同上。

```json
// 200
{ "id": "…", "role": "assistant", "content": "…", "tool_calls": [{ "name": "search_material", "args": { "keyword": "极限" } }],
  "prompt_tokens": 386, "completion_tokens": 26, "latency_ms": 3210, "created_at": "…" }
```

`tool_calls` 仅用于调试/演示展示，前端可忽略。

---

## 11. AI：总结 / 测试题 / 建议

> ⏱ **调用方可承受的长耗时**：本节的三个 `POST`（总结 / 出题 / 建议）都要等模型走完
> 「生成 + 结构化校验（必要时重试）」，后端单轮上限 `ai_agent_timeout` 90s。
> 前端**不要**用全局 15s 超时，本项目的做法是给这三个接口单独传 `timeout: 180000`（`frontend/src/api/ai.ts`），
> 列表与详情接口仍用 15s。踩过的坑：超时会先于后端返回，表现为「请求超时但记录其实已落库」。

### POST `/api/v1/ai/summaries`

```json
{ "material_id": "…", "scope_start": 0, "scope_end": null, "style": "outline" }
```

`style`：`outline`（提纲）/ `key_points`（要点）/ `detailed`（详解）。
`scope_start/scope_end` 为**字符偏移**，`null` 表示到末尾；区间超过 `LLM_MAX_INPUT_CHARS` 时后端自动分段汇总（响应 `mode` 字段标注 `direct` 或 `map_reduce`）。

```json
// 201
{
  "id": "…", "material_id": "…", "style": "outline", "mode": "map_reduce",
  "summary_md": "## 一、极限的定义\n…", "key_points": ["ε-δ 定义", "左右极限"],
  "char_count": 38210, "segments": 6, "model": "deepseek-chat",
  "prompt_tokens": 8123, "completion_tokens": 940, "latency_ms": 18400,
  "created_at": "2026-10-18T03:20:11Z"
}
```

失败：`422` 若 `material_id` 解析状态不是 `success`（`MAT_001`）；`502 AI_002`；`504 AI_003`。

### GET `/api/v1/ai/summaries`

Query：`material_id`、`page`、`size`。列表 item **不含** `summary_md`，只含 `key_points` 与元信息。

### GET `/api/v1/ai/summaries/{id}`

完整对象。

### POST `/api/v1/ai/quizzes`

```json
{ "material_id": "…", "title": null, "count": 5, "types": ["single", "judge"],
  "difficulty": "medium", "scope_start": 0, "scope_end": null }
```

约束：`count` 1-20；`types` ∈ `single`(单选) / `multiple`(多选) / `judge`(判断) / `blank`(填空)；`difficulty` ∈ `easy`/`medium`/`hard`。

```json
// 201
{
  "id": "…", "material_id": "…", "title": "高等数学 第一章 课后测验",
  "question_count": 5, "types": ["single", "judge"], "difficulty": "medium",
  "questions": [
    { "no": 1, "type": "single", "stem": "函数在一点连续的充要条件是？",
      "options": ["…", "…", "…", "…"], "answer": ["B"],
      "explanation": "…", "difficulty": "medium", "source_hint": "第 12 页" }
  ],
  "model": "deepseek-chat", "prompt_tokens": 4210, "completion_tokens": 880,
  "latency_ms": 12300, "created_at": "…"
}
```

- `answer` 统一为**字符串数组**：单选/判断长度 1，多选 1..n，填空为多个空的标准答案。
- `options` 对 `judge` 固定为 `["正确", "错误"]`；对 `blank` 为 `[]`。
- `source_hint` 可为 `null`；用于展示「出处」。
- 后端对 AI 结果做**业务二次校验**后才落库，失败重试一次，仍失败返回 502 `AI_001`。

### GET `/api/v1/quizzes`

Query：`material_id`、`page`、`size`。列表 item 不含 `options`/`answer`（防作弊），只含元信息。

### GET `/api/v1/quizzes/{id}`

Query：`with_answer`（默认 `true`）。
`with_answer=false` 时把每题的 `answer` 与 `explanation` 置为 `null`（用于答题页面）。

### POST `/api/v1/quizzes/{id}/attempts`

```json
{ "answers": [{ "no": 1, "answer": ["B"] }, { "no": 2, "answer": ["A", "C"] }], "duration_seconds": 240 }
```

```json
// 201
{
  "id": "…", "quiz_id": "…", "score": 80.0, "correct_count": 4, "question_count": 5,
  "duration_seconds": 240, "created_at": "…",
  "details": [{ "no": 1, "your_answer": ["B"], "correct_answer": ["B"], "is_correct": true, "explanation": "…" }]
}
```

判分规则：单选/判断全等得分；多选**完全一致**才算对（少选不得分，论文中需说明该策略）；填空去首尾空白 + 忽略大小写后比对。
`score = round(correct_count / question_count * 100, 1)`。

### GET `/api/v1/quizzes/{id}/attempts` / GET `/api/v1/attempts/{id}`

列表按 `created_at` 倒序；首次答题与重做都记录，统计取**每次**答卷（正确率 = 所有答卷的正确题数 / 总题数）。

### POST `/api/v1/ai/advice/generate`

```json
{ "days": 7, "focus": "review" }
```

`days` 1-90，取近 N 天统计；`focus` ∈ `review`(复习) / `plan`(规划) / `balance`(均衡)。

```json
// 201
{
  "id": "…", "period_days": 7, "focus": "review",
  "summary": "近 7 天共学习 6.2 小时，任务完成率 78%，但正确率仅 61%。",
  "suggestions": [
    { "title": "优先补极限与连续的错题", "reason": "该知识点近 7 天错 5 题", "action": "重做第一章测验", "priority": "high" }
  ],
  "weak_points": [{ "knowledge": "极限", "accuracy": 0.5, "attempts": 10 }],
  "next_7_days": [{ "date": "2026-10-19", "minutes": 60, "focus": "极限与连续" }],
  "model": "deepseek-chat", "latency_ms": 9500, "created_at": "…"
}
```

### GET `/api/v1/ai/advice`

返回最近一次建议（无记录时 `200 {"advice": null}`）；Query `stale_days`（默认 1）：超过该天数则响应加 `"stale": true`，前端提示「数据已过期，可重新生成」。

### GET `/api/v1/ai/advice/history`

分页返回历史建议概要。

---

## 12. 统计 `/stats` 与个性化推荐 `/recommendations`

### 12.1 学习数据统计（功能 11）

#### GET `/api/v1/stats/overview`

Query：`days`（默认 7，1..365）

```json
{
  "period": { "from": "2026-10-12", "to": "2026-10-18", "days": 7 },
  "total_minutes": 372, "active_days": 5, "streak_days": 3, "daily_avg_minutes": 53.1,
  "task_total": 18, "task_done": 14, "task_completion_rate": 0.78,
  "quiz_attempts": 6, "quiz_accuracy": 0.61,
  "materials": 4, "notes": 12, "ai_calls": 23
}
```

口径（与 `app/services/stats_service.py` 头部注释一一对应）：

- `task_total` **不含 skipped**；跳过不算失败，也不进完成率分母
- 所有日期按 `APP_TIMEZONE`（默认 `Asia/Shanghai`）切分，**不是 UTC**
- 无数据时各项为 `0`，`task_completion_rate` / `quiz_accuracy` 为 `0.0`（不是 `null`，也不除零）
- 与 agent 工具 `get_study_stats`（`docs/agent-tools.md` §3.4）返回**同一份聚合**，区别只是本接口不做工具信封包装

#### GET `/api/v1/stats/daily`

Query：`date_from`、`date_to`（默认近 30 天，区间 ≤ 365 天）

```json
{ "items": [{ "date": "2026-10-12", "minutes": 60, "task_total": 2, "task_done": 2, "quiz_attempts": 1, "quiz_accuracy": 0.8 }] }
```

> 无数据的日期**补零返回**（后端用 `generate_series` 补），前端不用自己补点，ECharts 直接画。

#### GET `/api/v1/stats/subjects`

Query：`date_from`、`date_to`

```json
{ "items": [{ "subject": "高数", "minutes": 240, "task_done": 9 }, { "subject": "未分类", "minutes": 132, "task_done": 5 }] }
```

> 科目取自计划的 `subject`（无计划归属的记录归入「未分类」）。

#### GET `/api/v1/stats/weak-points`

Query：`days`（默认 30，1..180）、`limit`（默认 5，1..10）

```json
{ "items": [{ "knowledge": "极限", "attempts": 10, "correct": 5, "accuracy": 0.5 }] }
```

> 知识点来源：`quiz.question_data` 中每题的 `knowledge` 标签（生成题目时要求模型给出）。
> 样本少于 3 次的知识点会被过滤（避免「做错 1 次就是薄弱点」）。

### 12.2 个性化学习推荐（功能 10）

功能 10 分两层实现，互不替代：

| 层 | 接口 | 特点 |
|---|---|---|
| **规则层**（本节） | `GET /api/v1/recommendations` | 秒回、可解释、可复现、**不调用大模型**、不消耗配额 |
| **AI 层**（M5 已实现） | `POST /api/v1/ai/advice/generate` | 由模型综合统计给出叙述性建议（见 §11） |

#### GET `/api/v1/recommendations`

Query：`limit`（默认 5，1..10）

```json
{
  "generated_at": "2026-10-19T17:20:00+08:00",
  "items": [
    {
      "kind": "task",
      "priority": 1,
      "title": "先完成「高数第三章 3.1」",
      "reason": "今天有 2 个任务未完成，其中 1 个已逾期",
      "action": "去做任务",
      "route": "/plans?tab=tasks",
      "ref_id": "0f2c…"
    }
  ]
}
```

`kind` 取值与触发条件（按 `priority` 升序返回，`limit` 截断）：

| kind | 触发条件 | 推荐内容 |
|---|---|---|
| `task` | 今天或更早的未完成任务 | 去完成最紧急的任务（逾期优先） |
| `review` | 近 30 天存在正确率 < 0.6 的薄弱知识点 | 复习该知识点所在资料 / 重做测试题 |
| `plan` | 有 `active` / 未开始的计划 | 推进计划（一键生成每日任务） |
| `material` | 有资料 `parse_status != success` | 重新解析资料（否则 AI 读不到正文） |
| `habit` | 近 7 天时长 < 每日目标 × 天数 × 0.5 | 降低启动门槛（先来 1 个 25 分钟番茄钟） |

- 无任何触发条件时返回 `items: []`（前端显示「状态不错，继续保持」）
- 每个 `kind` 最多出现 1 条；`route` 是前端可直接跳转的路径，`ref_id` 可为 `null`
- 不新增错误码（仅 401 / 422）

---

## 13. SSE 事件协议（问答流式）★

响应头：`Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
每 15s 发送一次注释行 `: ping` 作为心跳，防代理断连。

事件序列（`event:` 名 + `data:` JSON）：

```
event: meta
data: {"session_id":"…","message_id":"…","model":"deepseek-chat"}

event: tool
data: {"name":"search_material","args":{"keyword":"极限"},"status":"start"}
data: {"name":"search_material","status":"end","summary":"命中 2 段，共 812 字符"}

event: delta
data: {"text":"极限的"}

event: delta
data: {"text":"定义是…"}

event: done
data: {"message_id":"…","prompt_tokens":386,"completion_tokens":26,"total_tokens":412,"latency_ms":3210,"finish_reason":"stop"}

event: error
data: {"code":"AI_003","message":"AI 响应超时，请稍后重试"}
```

前端处理约定：
- 收到 `delta` 即追加渲染；`tool` 事件可显示「正在检索资料…」。
- 收到 `error` 后**必须**关闭连接并展示 `message`；已输出的内容保留。
- `done` 后关闭连接并让 TanStack Query 失效 `messages` 查询，以服务端持久化的内容为准。

> 实现提示：`EventSource` 只支持 GET，此处是 POST → 前端用 `fetch` + `ReadableStream` 解析，或 `@microsoft/fetch-event-source`。

---

## 14. AI 用量 `/ai/usage`

```json
// GET /api/v1/ai/usage?days=7
{ "days": 7, "today_calls": 6, "daily_quota": 100, "prompt_tokens": 18234,
  "completion_tokens": 4210, "total_tokens": 22444, "success_rate": 0.96,
  "items": [{ "date": "2026-10-18", "calls": 6, "total_tokens": 2100 }] }
```

---

## 15. 前端类型生成

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.d.ts
```

- 后端改接口后**必须**重跑一次并提交生成结果。
- 生成类型只覆盖请求/响应 DTO；`SSE 事件`、`错误码枚举`需手写在 `src/types/api.d.ts` 的扩展区（本文件 §13、§1.4）。

---

## 16. 功能 13：管理员端接口 ★

> 本文档 §3–§15 是**用户端**接口（数据严格按 `user_id` 隔离）；本节是**功能 13**（管理员端），一律挂在 `/api/v1/admin` 下，走独立的 `get_current_admin` 依赖（校验 `role='admin'` 且 `is_active=true`），非管理员访问 → 403 `AUTH_004`。
> 功能 13 子模块划分：13.1 仪表盘、13.2 用户管理、13.3 内容管理、13.4 AI 用量监控、13.5 系统配置与审计。

**两条纪律**
1. **所有管理端写操作必须写 `admin_audit_log`，且与业务变更在同一个事务里提交**（避免「改了但没记」）。
2. **管理端不提供任何 AI 生成类接口** —— 管理员不能批量生成内容。这既是成本控制，也是内容合规上的必要边界（论文里可明确写出这条设计取舍）。

### 16.1 仪表盘统计（功能 13.1）

`GET /api/v1/admin/stats/overview?days=30`

```json
{ "range": { "from": "2026-09-19", "to": "2026-10-18", "days": 30 },
  "users": { "total": 128, "active_7d": 64, "new_7d": 17, "disabled": 3, "admins": 1 },
  "content": { "materials": 412, "notes": 903, "plans": 88, "quizzes": 231 },
  "activity": { "study_minutes": 24800, "task_completion_rate": 0.74 },
  "ai": { "calls": 1820, "total_tokens": 4120000, "success_rate": 0.97, "today_calls": 96 } }
```

`GET /api/v1/admin/stats/daily?from=&to=` → `{ "items": [{ "date", "new_users", "active_users", "study_minutes", "ai_calls" }] }`（**无数据日期补零**，同用户端约定）

`GET /api/v1/admin/stats/ai?days=30`

```json
{ "by_scene": [{ "scene": "quiz", "calls": 420, "total_tokens": 980000, "success_rate": 0.98, "avg_latency_ms": 12400 }],
  "top_users": [{ "user_id": "…", "username": "zhangsan", "calls": 210, "total_tokens": 480000 }],
  "daily": [{ "date": "2026-10-18", "calls": 96, "total_tokens": 210000, "failed": 3 }] }
```

### 16.2 用户管理（功能 13.2）

`GET /api/v1/admin/users?page=&size=&keyword=&role=&is_active=&order=-created_at`

item 中的 `counts` 必须用**一条聚合子查询**取得，不允许逐行查询（N+1）：

```json
{ "id": "…", "username": "zhangsan", "email": "z@example.com", "nickname": "张三",
  "role": "user", "is_active": true, "disabled_reason": null,
  "created_at": "…", "last_login_at": "…",
  "counts": { "materials": 4, "notes": 12, "ai_calls_30d": 46, "study_minutes_30d": 372 } }
```

`GET /api/v1/admin/users/{id}` → 同上，另加 `quiz_accuracy_30d`、`ai_tokens_30d`。

`PATCH /api/v1/admin/users/{id}`

```json
{ "is_active": false, "disabled_reason": "上传违规内容", "role": "user" }
```

| 规则 | 说明 |
|---|---|
| 禁止操作自己 | 禁用 / 降级 / 重置密码 / 强制下线 自己 → 400 `ADMIN_001`（防把系统锁死） |
| 变更即下线 | `is_active` 或 `role` 变更 → `token_version + 1`，旧 token 立即失效 |
| 禁用必填原因 | `is_active=false` 时 `disabled_reason` 必填（≤200 字），该文案会展示给用户 |
| 角色白名单 | `role` 只能为 `user` / `admin` |
| 审计 | `user.disable` / `user.enable` / `user.role_change`，`detail` 记录前后快照 |

`POST /api/v1/admin/users/{id}/reset-password`

```json
// 200（仅此一次返回，服务端不存明文）
{ "temporary_password": "Tmp8f3kQ2z", "note": "请线下告知用户，首次登录后建议修改密码" }
```

生成 12 位随机密码 → `token_version + 1` 强制下线 → 审计 `user.reset_password`。**不发邮件**（毕设无邮件服务），由管理员线下转达。

`POST /api/v1/admin/users/{id}/revoke-tokens` → `204`，审计 `user.revoke_tokens`。

### 16.3 内容管理（功能 13.3）

| 接口 | 行为 |
|---|---|
| `GET /api/v1/admin/materials?keyword=&user_id=&parse_status=&file_ext=` | item 含 `owner: {id, username}` |
| `DELETE /api/v1/admin/materials/{id}` | `204`，软删除 + 删磁盘文件 + 审计 `material.delete` |
| `POST /api/v1/admin/materials/{id}/reparse` | `202`，审计 `material.reparse` |
| `GET /api/v1/admin/notes?keyword=&user_id=` | item 含 `excerpt` 与 `owner`；**不返回完整 `content`** |
| `DELETE /api/v1/admin/notes/{id}` | `204` + 审计 `note.delete` |
| `GET /api/v1/admin/quizzes?user_id=&material_id=` | item **不含** `questions`（防答案泄露面） |
| `DELETE /api/v1/admin/quizzes/{id}` | `204` + 审计 `quiz.delete` |

> **统计口径约定**：测试题被下架后，其历史答卷 `quiz_attempt` **保留并继续计入统计**。理由：下架是为了阻止内容继续被使用，而统计口径一旦随下架变动，历史报表就不可复现。这条要写进论文的「设计取舍」。

### 16.4 AI 调用明细（功能 13.4）

`GET /api/v1/admin/ai-usage?page=&size=&user_id=&scene=&ok=&date_from=&date_to=`

```json
{ "items": [{ "id": "…", "user": { "id": "…", "username": "zhangsan" }, "scene": "qa",
  "model": "deepseek-chat", "prompt_tokens": 3860, "completion_tokens": 420,
  "total_tokens": 4280, "steps": 3, "latency_ms": 8210, "ok": true,
  "error_code": null, "created_at": "…" }] }
```

### 16.5 系统配置（功能 13.5）

`GET /api/v1/admin/settings`

```json
{ "items": [{ "key": "ai.daily_quota", "value": 100, "value_type": "int",
  "description": "每用户每日 AI 调用上限", "editable": true,
  "updated_at": "…", "updated_by_username": "admin" }] }
```

`PATCH /api/v1/admin/settings`

```json
{ "items": [{ "key": "ai.daily_quota", "value": 200 }, { "key": "ai.enabled", "value": false }] }
```

| 规则 | 说明 |
|---|---|
| 仅可改 `editable=true` | `ai.model_name` 为只读（`editable=false`）——运行时切模型会导致历史 `model` 字段无法解释、计费口径漂移 |
| 按 `value_type` 校验 | `int` 范围 1..10000；`bool` 必须为布尔；`string` ≤200 字 |
| 缓存 | 写入后立即清除 60 秒进程内缓存 |
| 审计 | `setting.update`，`detail` 含 from/to 快照 |
| 关闭 AI | `ai.enabled=false` 后所有 AI 接口返回 503 `SYS_503`，前端置灰入口并提示「AI 功能已暂停」 |
| 关闭注册 | `register.allow=false` 后 `POST /auth/register` 返回 503 `SYS_503` |

### 16.6 操作审计（功能 13.5）

`GET /api/v1/admin/audit-logs?page=&size=&admin_id=&action=&target_type=&date_from=&date_to=`

```json
{ "items": [{ "id": "…", "admin": { "id": "…", "username": "admin" },
  "action": "user.disable", "target_type": "user", "target_id": "…",
  "detail": { "from": { "is_active": true }, "to": { "is_active": false, "disabled_reason": "上传违规内容" } },
  "ip": "127.0.0.1", "created_at": "…" }] }
```

审计日志**只增不改不删**，管理端不提供删除接口。

### 16.7 管理端前端约定（功能 13 前端部分）

- **同一个 React 应用**，不是第二个项目：路由 `/admin/*` + `RequireRole role="admin"` 守卫 + 独立 `AdminLayout`（左侧菜单 + 面包屑）。
- 用 `React.lazy` 拆成**独立 chunk**：普通用户不会下载管理端代码（首屏体积不变）。
- 入口只在 `role === 'admin'` 时显示（顶栏头像下拉菜单）。
- 进入 `/admin/*` 时**重新请求 `/users/me` 校验角色**，不能只信内存里的 `role`（覆盖「用户在另一个标签页被降权」的场景）。
- 管理端页面**不出现任何 AI 生成入口**（见本节开头第 2 条纪律）。

---

## 17. 契约自检清单（每次改接口前过一遍）

- [ ] 新字段是否已在本文件登记？（请求 / 响应 / 错误码）
- [ ] 列表接口是否用了统一分页结构？大字段（正文、答案、`summary_md`）是否已从列表里排除？
- [ ] 涉及他人资源时是否按「越权返回 404」处理？
- [ ] 该接口的 `user_id` 过滤是否写在 SQL 里（而非查出来再判断）？
- [ ] 是否会影响 `/docs` 的示例（Swagger 是交付物，示例要好看）？
- [ ] 是否新增了 agent 工具所需的字段？若有，同步更新 `docs/agent-tools.md`。
- [ ] 新增的是**管理端**接口吗？如果是：路径是否在 `/api/v1/admin` 下、是否走 `get_current_admin`、404 与 403 的取舍是否正确（用户端越权 404 / 管理端角色不足 403）？
- [ ] 管理端写操作是否已登记 `action` 常量并在**同一事务**内写 `admin_audit_log`？
- [ ] 是否涉及「管理员操作自己」？应当拒绝并返回 400 `ADMIN_001`。
- [ ] 管理端列表是否返回了不该给管理员的用户隐私内容（完整笔记正文、题目答案、`password_hash`）？
