# 数据库设计（PostgreSQL 18）

> 项目：智能学习系统 ｜ 更新：2026-10-18
> 本文档定义表、字段、类型、约束与索引，是 Alembic 迁移与 SQLModel 模型的唯一依据。

---

## 1. 全局约定

| 项 | 约定 | 理由 |
|---|---|---|
| 库名 / 字符集 | `smart_learning` / UTF8 | — |
| 表名 | 单数 snake_case；用户表用 **`app_user`** | `user` 是 SQL 保留字，避免到处加引号 |
| 主键 | `id UUID`，Python 侧 `default_factory=uuid4` | 不依赖 DB 默认值，测试可预测、数据可迁移 |
| 时间 | `TIMESTAMPTZ`，统一存 UTC | 客户端按本地时区展示 |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL`；`updated_at` 由**应用层**维护 | 不建数据库触发器，逻辑集中在 service 层 |
| 枚举 | **`VARCHAR` + `CHECK` 约束**，不用 PG 原生 `ENUM` | SQLModel/Alembic autogenerate 对原生枚举支持差（见技术栈 §8.3） |
| 软删除 | `deleted_at TIMESTAMPTZ NULL`，仅特定表有 | 查询统一带 `deleted_at IS NULL` |
| 标签数组 | `tags TEXT[]` + GIN 索引 | 比 `JSONB` 更适合集合包含查询 |
| 布尔 | `BOOLEAN NOT NULL DEFAULT false` | — |
| 金额/比率 | 不适用；比率只在**响应时计算**，不落库 | 避免冗余不一致 |
| 统计冗余列 | **不设**（如 `plan.task_done`），一律聚合查询 | 毕设数据量小，正确性优先 |

**扩展**（写在第一个迁移里）：`CREATE EXTENSION IF NOT EXISTS pg_trgm;`（中文模糊搜索）
`gen_random_uuid()` 自 PG13 起为内置函数，无需 `pgcrypto`。

**连接与池**：`asyncpg` + `create_async_engine(pool_size=10, max_overflow=20, pool_pre_ping=True)`。

### 1.1 开发环境的认证口径（实测，容易误解）

官方 `postgres` 镜像生成的 `pg_hba.conf` 对**本机连接**是 `trust`：

```text
local  all  all            trust
host   all  all  127.0.0.1 trust
host   all  all  ::1       trust
host   all  all  all       scram-sha-256   ← 只有非本机连接才校验密码
```

推论（都已实测验证）：

| 现象 | 说明 |
|---|---|
| `PGPASSWORD=错的` 也能从本机连上 | 因为 localhost 走 `trust`，`app:app` 这个密码在本机**不会被校验** |
| `POSTGRES_PASSWORD` 只对**首次初始化**生效 | 密码存在卷里的 `pg_authid`；改 compose 后重启容器，密码不会变 |
| 端口只绑 `127.0.0.1:5432` | 局域网/外网连不进来，所以开发环境是可接受的 |

> ⚠️ **不要用「改了密码还能连」判断配置没生效** —— 在本机它本来就不校验。
> 也**不要**把这套配置用于公网部署。

**生产硬化清单（M7 部署时执行）**

1. `POSTGRES_HOST_AUTH_METHOD: scram-sha-256`（只对新建卷生效；已有卷需重建或改 `pg_hba.conf` 后 `pg_reload_conf()`）
2. `ALTER USER app WITH PASSWORD '<强随机密码>'` 并同步 `DATABASE_URL`
3. **不**对宿主机暴露 5432（仅在 compose 内部网络可达）
4. 应用改用**最小权限角色**（`app` 现在是 Superuser，只适合开发）

> 补充：应用层密码（用户登录）与数据库认证是两套东西 —— 前者校验 `app_user.password_hash` 里的 Argon2id 哈希，与 `pg_hba.conf` 无关。

---

## 2. 表清单（14 张）

| # | 表 | 用途 | 软删除 |
|---|---|---|---|
| 1 | `app_user` | 用户与认证信息（含角色） | 否 |
| 2 | `material` | 学习资料元数据 + 解析正文 | 是 |
| 3 | `note` | 在线笔记 | 是 |
| 4 | `study_plan` | 学习计划 | 是 |
| 5 | `study_task` | 每日学习任务 | 是 |
| 6 | `study_record` | 学习记录（时长流水） | 是 |
| 7 | `chat_session` | AI 问答会话 | 是 |
| 8 | `chat_message` | 问答消息 | 随会话级联 |
| 9 | `quiz` | AI 生成的测试题 | 是 |
| 10 | `quiz_attempt` | 答卷与判分结果 | 否（统计依据） |
| 11 | `ai_generation` | AI 生成物归档（总结 / 建议） | 否 |
| 12 | `ai_usage` | AI 调用流水（token、配额） | 否 |
| 13 | `app_setting` | 系统配置（全局配额、开关） | 否 |
| 14 | `admin_audit_log` | 管理员操作审计日志 | 否 |

**为什么管理员端只加 2 张表**：功能 13（管理员端）的绝大部分能力（用户、资料、笔记、测试题、AI 用量）都是**对已有表的跨用户读写**，不需要新表；真正新增的只有「可调系统配置」和「操作审计」两件事。这也说明管理端的工作量主要在接口与页面，而不是数据建模。

**为什么测试题单独建表、总结和建议合并进 `ai_generation`**：
测试题有独立的答题与判分语义（需要 `quiz_attempt`），且前端有独立的答题流程；而总结与建议只是「一次生成的文本 + 结构化数据」，共用一个归档表即可，避免表数量膨胀。

---

## 3. 表结构

### 3.1 `app_user`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `username` | VARCHAR(32) | NOT NULL, UNIQUE | 3-32 位 `[A-Za-z0-9_]`，应用层校验 |
| `email` | VARCHAR(254) | NOT NULL, UNIQUE | 应用层做大小写归一（存小写） |
| `password_hash` | VARCHAR(255) | NOT NULL | pwdlib + Argon2id，**永不出现在响应中** |
| `nickname` | VARCHAR(32) | NULL | 缺省展示 `username` |
| `avatar_url` | VARCHAR(512) | NULL | 相对路径 |
| `learning_goal` | VARCHAR(200) | NULL | 学习目标 |
| `daily_target_minutes` | SMALLINT | NOT NULL DEFAULT 60, CHECK 1..1440 | 每日目标 |
| `role` | VARCHAR(16) | NOT NULL DEFAULT `'user'`, CHECK IN (`user`,`admin`) | 角色；**权限判定一律读库，不信 JWT 中的角色声明** |
| `is_active` | BOOLEAN | NOT NULL DEFAULT true | 禁用即置 false |
| `disabled_at` | TIMESTAMPTZ | NULL | 禁用时间 |
| `disabled_reason` | VARCHAR(200) | NULL | 禁用原因（管理员填写，展示给用户） |
| `token_version` | SMALLINT | NOT NULL DEFAULT 0 | JWT 携带 `pv`；改密码 / 改角色 / 强制下线时 +1 → 旧 token 全部失效 |
| `last_login_at` | TIMESTAMPTZ | NULL | — |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |

索引：`UNIQUE(username)`、`UNIQUE(email)`。

> **令牌吊销说明**：JWT 无状态，无法逐条吊销。本项目用 `token_version` 实现「改密码 / 改角色 / 管理员强制下线 = 全局下线」；登出仅清 Cookie。若需精确吊销单个设备，再引入 `refresh_token` 表（列为可选优化，不计入必修范围）。

### 3.2 `material`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | 归属 |
| `title` | VARCHAR(200) | NOT NULL | 缺省取文件名 |
| `subject` | VARCHAR(64) | NULL | 科目，用于统计/推荐 |
| `tags` | TEXT[] | NOT NULL DEFAULT `'{}'` | GIN 索引 |
| `file_name` | VARCHAR(255) | NOT NULL | 原始文件名（含扩展名） |
| `file_ext` | VARCHAR(8) | NOT NULL, CHECK IN (`.pdf`,`.docx`) | — |
| `mime_type` | VARCHAR(128) | NOT NULL | — |
| `size_bytes` | BIGINT | NOT NULL, CHECK > 0 | — |
| `file_path` | VARCHAR(512) | NOT NULL | 相对 `storage/` 的路径，**不返回前端** |
| `file_hash` | VARCHAR(64) | NOT NULL | SHA-256；用于提示重复上传 |
| `page_count` | SMALLINT | NULL | 解析后填充 |
| `char_count` | INTEGER | NULL | 提取字符数 |
| `extracted_text` | TEXT | NULL | 解析正文；**任何接口都不直接从这张表返回** |
| `parse_status` | VARCHAR(16) | NOT NULL DEFAULT `'pending'`, CHECK IN (`pending`,`parsing`,`success`,`failed`,`unsupported`) | — |
| `parse_error` | TEXT | NULL | 失败原因摘要（≤500 字） |
| `parsed_at` | TIMESTAMPTZ | NULL | — |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | 软删除 |

索引：
- `idx_material_user_created (user_id, created_at DESC) WHERE deleted_at IS NULL`
- `idx_material_user_subject (user_id, subject) WHERE deleted_at IS NULL`
- `idx_material_tags GIN (tags)`
- `idx_material_title_trgm GIN (title gin_trgm_ops) WHERE deleted_at IS NULL`
- `idx_material_user_hash (user_id, file_hash)`

> **正文为何不建全文索引**：单个资料正文可达数十万字符，`gin_trgm_ops` 索引体积过大。当前规模（单用户 ≤ 数十份资料）下，`search_material` 工具用 `ILIKE` 扫描 + `LIMIT` 已足够。
> **可选升级**：新增 `material_chunk(material_id, seq, content, tsvector)` 分段表并建 GIN 索引，检索精度与性能都会更好——这是「向量检索/RAG」之前的低门槛优化，可写进论文展望。

### 3.3 `note`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `material_id` | UUID | NULL, FK→`material.id` **ON DELETE SET NULL** | 可选关联资料 |
| `title` | VARCHAR(200) | NOT NULL | — |
| `content` | TEXT | NOT NULL DEFAULT `''` | Markdown，≤100000 字 |
| `tags` | TEXT[] | NOT NULL DEFAULT `'{}'` | — |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引：
- `idx_note_user_updated (user_id, updated_at DESC) WHERE deleted_at IS NULL`
- `idx_note_tags GIN (tags)`
- `idx_note_title_trgm GIN (title gin_trgm_ops)`
- `idx_note_content_trgm GIN (content gin_trgm_ops)`（笔记正文较短，可安全建 trgm 索引）

### 3.4 `study_plan`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `title` | VARCHAR(200) | NOT NULL | — |
| `subject` | VARCHAR(64) | NULL | — |
| `goal` | VARCHAR(500) | NULL | — |
| `start_date` / `end_date` | DATE | NOT NULL | 后者 ≥ 前者，区间 ≤180 天（应用层校验） |
| `daily_minutes` | SMALLINT | NOT NULL DEFAULT 60, CHECK 1..600 | — |
| `status` | VARCHAR(16) | NOT NULL DEFAULT `'active'`, CHECK IN (`draft`,`active`,`done`,`archived`) | — |
| `material_ids` | UUID[] | NOT NULL DEFAULT `'{}'` | 关联资料（见下方说明） |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引：`idx_plan_user_status (user_id, status, created_at DESC) WHERE deleted_at IS NULL`、`idx_plan_material_ids GIN (material_ids)`。

> **`material_ids` 用数组而非关联表**：该字段只用于展示与过滤，不需要外键完整性；用数组可少一张表、少一次 join。代价是资料被删除后会留下悬空 UUID，读取时按 `material` 表过滤即可。
> 若答辩要求严格 3NF，可升级为 `study_plan_material(plan_id, material_id)` 关联表（预计改动 30 分钟）。

### 3.5 `study_task`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | 冗余自 plan，便于直接按用户查询 |
| `plan_id` | UUID | NULL, FK→`study_plan.id` **ON DELETE CASCADE** | 允许独立任务 |
| `material_id` | UUID | NULL, FK→`material.id` **ON DELETE SET NULL** | 可选 |
| `plan_date` | DATE | NOT NULL | 任务的归属日 |
| `title` | VARCHAR(200) | NOT NULL | — |
| `description` | TEXT | NULL | — |
| `order_no` | SMALLINT | NOT NULL DEFAULT 1 | 当日序号 |
| `est_minutes` | SMALLINT | NOT NULL DEFAULT 30, CHECK 1..600 | 预计时长 |
| `status` | VARCHAR(16) | NOT NULL DEFAULT `'pending'`, CHECK IN (`pending`,`doing`,`done`,`skipped`) | — |
| `completed_at` | TIMESTAMPTZ | NULL | 置 `done` 时写入 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引与约束：
- **部分唯一索引**：`UNIQUE (plan_id, plan_date) WHERE plan_id IS NOT NULL AND deleted_at IS NULL` → 保证「同一计划的同一天只有一条任务」，是生成任务的幂等基础
- `idx_task_user_date (user_id, plan_date DESC) WHERE deleted_at IS NULL`
- `idx_task_user_status_date (user_id, status, plan_date) WHERE deleted_at IS NULL`

> 注意：**普通 UNIQUE 约束会把软删除的行也算进去**，导致删了任务后无法重建同一天的任务。必须用 PG 的部分唯一索引（SQLAlchemy：`Index(..., unique=True, postgresql_where=...)`）。

### 3.6 `study_record`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `task_id` | UUID | NULL, FK→`study_task.id` **ON DELETE SET NULL** | 由任务完成产生 |
| `material_id` | UUID | NULL, FK→`material.id` **ON DELETE SET NULL** | — |
| `type` | VARCHAR(16) | NOT NULL DEFAULT `'reading'`, CHECK IN (`reading`,`video`,`practice`,`review`,`other`) | — |
| `started_at` | TIMESTAMPTZ | NOT NULL | 学习开始时间（统计的基准时间） |
| `duration_minutes` | SMALLINT | NOT NULL, CHECK 1..1440 | — |
| `content` | VARCHAR(500) | NULL | 学了什么 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引：
- `idx_record_user_started (user_id, started_at DESC) WHERE deleted_at IS NULL` ← 用户端统计主索引
- `idx_record_started (started_at DESC) WHERE deleted_at IS NULL` ← **管理端全站趋势**（跨用户，复合索引无法服务纯时间范围扫描）
- `idx_record_task (task_id)`

### 3.7 `chat_session`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `material_id` | UUID | NULL, FK→`material.id` **ON DELETE SET NULL** | 限定资料；NULL = 全库检索 |
| `title` | VARCHAR(200) | NOT NULL DEFAULT `'新会话'` | 取首问前 20 字 |
| `message_count` | INTEGER | NOT NULL DEFAULT 0 | 冗余计数，避免列表页 N+1 聚合 |
| `last_message_at` | TIMESTAMPTZ | NULL | 列表排序用 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引：`idx_session_user_last (user_id, last_message_at DESC NULLS LAST) WHERE deleted_at IS NULL`。

### 3.8 `chat_message`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `session_id` | UUID | NOT NULL, FK→`chat_session.id` **ON DELETE CASCADE** | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | 便于越权校验 |
| `role` | VARCHAR(16) | NOT NULL, CHECK IN (`user`,`assistant`) | **`tool`/`system` 中间消息不落库** |
| `content` | TEXT | NOT NULL | — |
| `tool_calls` | JSONB | NULL | 该轮实际调用的工具，形如 `[{"name":"search_material","args":{"keyword":"极限"}}]`，供演示与调试 |
| `prompt_tokens` / `completion_tokens` | INTEGER | NOT NULL DEFAULT 0 | 仅 assistant 消息有值 |
| `latency_ms` | INTEGER | NULL | — |
| `created_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | 随会话级联软删 |

索引：`idx_msg_session_created (session_id, created_at)`、`idx_msg_user (user_id)`。

### 3.9 `quiz`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `material_id` | UUID | NULL, FK→`material.id` **ON DELETE SET NULL** | — |
| `title` | VARCHAR(200) | NOT NULL | — |
| `question_count` | SMALLINT | NOT NULL | — |
| `types` | TEXT[] | NOT NULL | 如 `{single,judge}` |
| `difficulty` | VARCHAR(8) | NOT NULL, CHECK IN (`easy`,`medium`,`hard`) | — |
| `question_data` | JSONB | NOT NULL | 题目数组，结构见 §4.1 |
| `model` | VARCHAR(64) | NOT NULL | 生成所用模型 |
| `prompt_tokens` / `completion_tokens` | INTEGER | NOT NULL DEFAULT 0 | — |
| `latency_ms` | INTEGER | NULL | — |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | — |
| `deleted_at` | TIMESTAMPTZ | NULL | — |

索引：`idx_quiz_user_created (user_id, created_at DESC) WHERE deleted_at IS NULL`、`idx_quiz_material (material_id)`。

### 3.10 `quiz_attempt`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `quiz_id` | UUID | NOT NULL, FK→`quiz.id` **ON DELETE CASCADE** | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `answers` | JSONB | NOT NULL | 用户作答，结构见 §4.2 |
| `score` | NUMERIC(5,2) | NOT NULL, CHECK 0..100 | — |
| `correct_count` | SMALLINT | NOT NULL | — |
| `question_count` | SMALLINT | NOT NULL | 冗余，便于统计 |
| `duration_seconds` | INTEGER | NULL | — |
| `created_at` | TIMESTAMPTZ | NOT NULL | 不软删 |

索引：`idx_attempt_quiz_created (quiz_id, created_at DESC)`、`idx_attempt_user_created (user_id, created_at DESC)`。

### 3.11 `ai_generation`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `scene` | VARCHAR(16) | NOT NULL, CHECK IN (`summary`,`advice`) | 生成场景 |
| `ref_type` | VARCHAR(16) | NOT NULL, CHECK IN (`material`,`user`) | 归档对象类型 |
| `ref_id` | UUID | NULL | 无外键（多态）；`summary` 指向 material |
| `input_params` | JSONB | NOT NULL DEFAULT `'{}'` | 如 `{"style":"outline","scope_start":0}` |
| `output_md` | TEXT | NULL | Markdown 正文（总结 / 建议全文） |
| `output_data` | JSONB | NULL | 结构化结果，结构见 §4.3、§4.4 |
| `model` | VARCHAR(64) | NOT NULL | — |
| `prompt_tokens` / `completion_tokens` | INTEGER | NOT NULL DEFAULT 0 | — |
| `latency_ms` | INTEGER | NULL | — |
| `created_at` | TIMESTAMPTZ | NOT NULL | 不软删（历史记录，可对比多次生成） |

索引：`idx_aigen_user_scene_created (user_id, scene, created_at DESC)`、`idx_aigen_ref (ref_type, ref_id)`。

### 3.12 `ai_usage`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `user_id` | UUID | NOT NULL, FK→`app_user.id` | — |
| `scene` | VARCHAR(16) | NOT NULL, CHECK IN (`qa`,`summary`,`quiz`,`advice`) | — |
| `model` | VARCHAR(64) | NOT NULL | — |
| `prompt_tokens` | INTEGER | NOT NULL DEFAULT 0 | **agent 多轮累加值** |
| `completion_tokens` | INTEGER | NOT NULL DEFAULT 0 | 同上 |
| `total_tokens` | INTEGER | NOT NULL DEFAULT 0 | 生成列或应用层计算 |
| `steps` | SMALLINT | NOT NULL DEFAULT 1 | agent 实际步数（工具调用轮次 +1），用于观察成本 |
| `latency_ms` | INTEGER | NULL | 整次调用耗时 |
| `ok` | BOOLEAN | NOT NULL | 成功与否 |
| `error_code` | VARCHAR(16) | NULL | 如 `AI_003` |
| `created_at` | TIMESTAMPTZ | NOT NULL | 配额按此字段的当日计数 |

索引：`idx_usage_user_created (user_id, created_at DESC)`、`idx_usage_scene_created (scene, created_at DESC)`、`idx_usage_created (created_at DESC)` ← **管理端全站统计**。

> **一次请求写一行**（不是一次模型调用写一行）：agent 的多轮 token 在应用层累加后写入。配额检查 = `SELECT count(*) FROM ai_usage WHERE user_id=? AND created_at >= today_start`。

### 3.13 `app_setting`

可调系统配置。用 KV 而非单行宽表：加配置不需要迁移。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `key` | VARCHAR(64) | PK | 配置键 |
| `value` | JSONB | NOT NULL | 配置值（统一用 JSONB，标量也包一层） |
| `value_type` | VARCHAR(16) | NOT NULL, CHECK IN (`int`,`bool`,`string`,`json`) | 供管理端表单渲染与校验 |
| `description` | VARCHAR(200) | NOT NULL | 中文说明，直接展示给管理员 |
| `updated_by` | UUID | NULL, FK→`app_user.id` | 最后修改人 |
| `updated_at` | TIMESTAMPTZ | NOT NULL | — |

初始数据（写在 `0006_admin` 迁移的 `upgrade()` 里）：

| key | value | value_type | 说明 |
|---|---|---|---|
| `ai.daily_quota` | `100` | int | 每用户每日 AI 调用上限（`app_setting` 优先于 `.env`） |
| `ai.enabled` | `true` | bool | 全局 AI 功能开关（关闭后所有 AI 接口返回 503） |
| `ai.model_name` | `"deepseek-chat"` | string | 展示用；**不允许在管理端改**（改模型必须走部署配置） |
| `register.allow` | `true` | bool | 是否开放注册 |
| `upload.max_mb` | `20` | int | 单文件大小上限 |

> **为什么 `ai.model_name` 不可改**：允许在运行时切模型会导致「历史数据的 model 字段无法解释」和「计费口径漂移」。管理端只读展示，改模型走 `.env` + 重启（论文里可作为「配置治理」的讨论点）。
> **为什么需要 `app_setting` 而不是只用 `.env`**：`.env` 改一次要重启服务，而「临时把某个开关关掉」是管理端的真实需求。读取时加 60 秒进程内缓存，避免每次请求打库。

### 3.14 `admin_audit_log`

管理员操作审计。**只增不改不删**，是答辩时很好讲的一个点。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | UUID | PK | — |
| `admin_id` | UUID | NOT NULL, FK→`app_user.id` | 操作人；管理员被禁用也不影响日志 |
| `action` | VARCHAR(48) | NOT NULL | 见下表（字符串常量，不用 CHECK 枚举，便于扩展） |
| `target_type` | VARCHAR(24) | NOT NULL, CHECK IN (`user`,`material`,`note`,`quiz`,`setting`,`system`) | 操作对象类型 |
| `target_id` | UUID | NULL | 操作对象 ID（`setting` 类为空） |
| `detail` | JSONB | NOT NULL DEFAULT `'{}'` | 变更前后快照，如 `{"from":{"is_active":true},"to":{"is_active":false}}` |
| `ip` | INET | NULL | 操作来源 IP |
| `user_agent` | VARCHAR(255) | NULL | — |
| `created_at` | TIMESTAMPTZ | NOT NULL | — |

索引：`idx_audit_created (created_at DESC)`、`idx_audit_admin_created (admin_id, created_at DESC)`、`idx_audit_target (target_type, target_id)`。

`action` 取值（应用层常量，不落 CHECK）：

| action | 触发时机 |
|---|---|
| `user.disable` / `user.enable` | 启用 / 禁用用户 |
| `user.role_change` | 修改角色 |
| `user.reset_password` | 重置密码 |
| `user.revoke_tokens` | 强制下线 |
| `material.delete` / `material.reparse` | 下架 / 重新解析资料 |
| `note.delete` / `quiz.delete` | 删除违规内容 |
| `setting.update` | 修改系统配置 |

> **审计日志写入时机**：与业务变更在**同一个数据库事务**里提交，避免「改了但没记」。审核边界：管理员**不能禁用自己、不能移除自己的 admin 角色、不能重置自己的密码**（防误操作把自己锁死），这类请求直接 400 `ADMIN_001`。

---

## 4. JSONB 结构定义

### 4.1 `quiz.question_data`

```json
[
  {
    "no": 1,
    "type": "single",
    "stem": "函数在一点连续的充要条件是？",
    "options": ["...", "...", "...", "..."],
    "answer": ["B"],
    "explanation": "连续性要求左极限 = 右极限 = 函数值。",
    "difficulty": "medium",
    "knowledge": "函数的连续性",
    "source_hint": "第 12 页"
  }
]
```

字段约束（服务层二次校验，不通过则重试生成）：

| 字段 | 约束 |
|---|---|
| `no` | 1..count，且不重复 |
| `type` | `single` / `multiple` / `judge` / `blank` |
| `stem` | 非空，≤500 字 |
| `options` | `single`/`multiple`：4 项非空且互不相同；`judge`：固定 `["正确","错误"]`；`blank`：`[]` |
| `answer` | 字符串数组；`single`/`judge` 长度为 1；`multiple` 长度 ≥1 且全部 ∈ 选项；`blank` 与空数一致 |
| `explanation` | 非空 |
| `knowledge` | 非空（薄弱知识点统计依赖它） |
| `source_hint` | 可为 `null` |

### 4.2 `quiz_attempt.answers`

```json
[{ "no": 1, "answer": ["B"], "is_correct": true }, { "no": 2, "answer": ["A", "C"], "is_correct": false }]
```

### 4.3 `ai_generation.output_data`（`scene=summary`）

```json
{ "key_points": ["ε-δ 定义", "左右极限"], "style": "outline", "mode": "map_reduce",
  "segments": 6, "char_count": 38210, "scope": { "start": 0, "end": null } }
```

### 4.4 `ai_generation.output_data`（`scene=advice`）

```json
{
  "summary": "近 7 天共学习 6.2 小时，任务完成率 78%，但正确率仅 61%。",
  "suggestions": [{ "title": "优先补极限与连续的错题", "reason": "该知识点近 7 天错 5 题", "action": "重做第一章测验", "priority": "high" }],
  "weak_points": [{ "knowledge": "极限", "accuracy": 0.5, "attempts": 10 }],
  "next_7_days": [{ "date": "2026-10-19", "minutes": 60, "focus": "极限与连续" }],
  "stats_snapshot": { "total_minutes": 372, "task_completion_rate": 0.78, "quiz_accuracy": 0.61, "streak_days": 3 },
  "period_days": 7, "focus": "review"
}
```

> `stats_snapshot` 是生成建议时的统计快照 → 让「建议 vs 实际数据」可追溯，答辩时能解释建议依据。

---

## 5. 实体关系（论文 E-R 图依据）

```
app_user 1 ──< material          (material.user_id)
app_user 1 ──< note              (note.user_id)
app_user 1 ──< study_plan        (study_plan.user_id)
app_user 1 ──< study_task        (study_task.user_id)
app_user 1 ──< study_record      (study_record.user_id)
app_user 1 ──< chat_session      (chat_session.user_id)
app_user 1 ──< quiz              (quiz.user_id)
app_user 1 ──< quiz_attempt      (quiz_attempt.user_id)
app_user 1 ──< ai_generation     (ai_generation.user_id)
app_user 1 ──< ai_usage          (ai_usage.user_id)

material 1 ──< note             (ON DELETE SET NULL)
material 1 ──< study_task       (ON DELETE SET NULL)
material 1 ──< study_record     (ON DELETE SET NULL)
material 1 ──< quiz              (ON DELETE SET NULL)
material 0..1 ──< study_plan    (material_ids UUID[]，无外键)
material 1 ──< chat_session      (ON DELETE SET NULL)

study_plan 1 ──< study_task      (ON DELETE CASCADE)
study_task 1 ──< study_record    (ON DELETE SET NULL)

chat_session 1 ──< chat_message  (ON DELETE CASCADE)
quiz 1 ──< quiz_attempt          (ON DELETE CASCADE)

ai_generation.ref_id → material | app_user   (多态，无外键)

admin_audit_log.admin_id → app_user          (审计日志)
app_setting.updated_by    → app_user          (可为 NULL)
```

> 所有业务表的读取都必须带 `user_id = :current_user_id`，即「每条查询自带租户过滤」。这是权限设计的第一道防线（详见技术栈 §3.3）。

---

## 6. 关键查询模式（统计与检索）

```sql
-- 每日学习时长趋势（补零，前端不用自己补点）
WITH days AS (
  SELECT generate_series(:from::date, :to::date, '1 day')::date AS d
)
SELECT d AS date,
       COALESCE(SUM(sr.duration_minutes), 0) AS minutes
FROM days
LEFT JOIN study_record sr
       ON sr.started_at::date = d
      AND sr.user_id = :uid
      AND sr.deleted_at IS NULL
GROUP BY d ORDER BY d;

-- 任务完成率
SELECT count(*) FILTER (WHERE status = 'done')::float / NULLIF(count(*), 0) AS rate
FROM study_task
WHERE user_id = :uid AND plan_date BETWEEN :from AND :to
  AND status <> 'skipped' AND deleted_at IS NULL;

-- 薄弱知识点（从 JSONB 展开）
SELECT qe.item ->> 'knowledge' AS knowledge,
       count(*) AS attempts,
       count(*) FILTER (WHERE pa.is_correct) AS correct
FROM quiz_attempt a
JOIN quiz q ON q.id = a.quiz_id
CROSS JOIN LATERAL jsonb_array_elements(a.answers) AS pa
JOIN LATERAL jsonb_array_elements(q.question_data) AS qe
     ON (qe.item ->> 'no')::int = (pa ->> 'no')::int
WHERE a.user_id = :uid AND a.created_at >= now() - make_interval(days => :days)
GROUP BY 1 ORDER BY (correct::float / count(*)) ASC LIMIT :limit;
```

> 中文模糊搜索统一用 `ILIKE '%kw%'` + `gin_trgm_ops` 索引；不使用 `to_tsvector`（中文分词缺失，反而更慢更不准）。

```sql
-- 管理端：全站 AI 用量 Top 用户（服务 idx_usage_created）
SELECT u.id, u.username,
       count(*)         AS calls,
       sum(au.total_tokens) AS total_tokens
FROM ai_usage au
JOIN app_user u ON u.id = au.user_id
WHERE au.created_at >= now() - make_interval(days => :days)
GROUP BY u.id, u.username
ORDER BY total_tokens DESC
LIMIT 10;

-- 管理端：全站每日趋势（补零，服务 idx_record_started / idx_usage_created）
WITH days AS (SELECT generate_series(:from::date, :to::date, '1 day')::date AS d)
SELECT d AS date,
       COALESCE((SELECT sum(duration_minutes) FROM study_record sr
                 WHERE sr.started_at::date = d AND sr.deleted_at IS NULL), 0) AS study_minutes,
       COALESCE((SELECT count(*) FROM ai_usage au
                 WHERE au.created_at::date = d), 0) AS ai_calls
FROM days ORDER BY d;
```

> 管理端统计会跨用户扫描，因此 `study_record.started_at` 与 `ai_usage.created_at` 上都单列了索引（复合索引 `(user_id, ...)` 无法服务纯时间范围查询）。

---

## 7. SQLModel / PG 落地注意事项

| 需求 | 写法 |
|---|---|
| `JSONB` 列 | `sa_column=Column(JSONB)`（`from sqlalchemy.dialects.postgresql import JSONB`），不要用 `JSON`（会退化成文本） |
| `TEXT[]` 列 | `sa_column=Column(ARRAY(Text), nullable=False, server_default=text("'{}'"))` |
| 部分唯一索引 | `__table_args__ = (Index("uq_task_plan_date", "plan_id", "plan_date", unique=True, postgresql_where=text("plan_id IS NOT NULL AND deleted_at IS NULL")),)` |
| `CHECK` 约束 | `sa_column=Column(String(16), CheckConstraint(...))`，或在 `__table_args__` 里统一声明 |
| `TIMESTAMPTZ` | `datetime` + `sa_type=DateTime(timezone=True)` |
| `NUMERIC(5,2)` | `Decimal` + `sa_column=Column(Numeric(5, 2))` |
| 枚举字段 | 用 `str` + CHECK，**不要** `Enum` 类型（见 §1） |
| 软删除过滤 | 所有查询显式 `.where(X.deleted_at.is_(None))`；在 service 层封装 `not_deleted(stmt)` 辅助函数，禁止散落判断 |

**迁移纪律**：
1. `models/__init__.py` 统一导出全部模型 → `alembic/env.py` 只 import 该包。
2. `alembic revision --autogenerate -m "..."` 后**必须人工审阅**，重点检查：partial index 是否生成、CHECK 约束是否丢失、`JSONB`/`ARRAY` 类型是否正确。
3. 第一个迁移包含 `CREATE EXTENSION IF NOT EXISTS pg_trgm`（放在 `upgrade()` 开头）。
4. **迁移文件名**：`%Y%m%d_<rev>_<slug>.py`（`alembic.ini` 的 `file_template`），按日期排序，便于论文中按阶段展示数据库演进。已有：`20261018_161c601b0154_init_pg_trgm_extension.py`。后续按功能批次命名（如 `..._material`、`..._note`、`..._plan_task`、`..._ai`、`..._admin`）。
   > ⚠️ `alembic.ini` **必须保持纯 ASCII**：configparser 以系统 locale 编码读取，中文注释在中文 Windows（GBK）下会直接抛 `UnicodeDecodeError`。注释请写英文。

---

## 8. 初始化与测试数据

- 开发环境用 `alembic upgrade head` 建表；**不提供** seed 脚本自动插业务数据。
- `0006_admin`（`20261019_3b81d0dc7f6c_admin`）的 `upgrade()` 会插入 5 条 `app_setting` 初始配置
  （`ai.daily_quota` / `ai.enabled` / `ai.model_name` / `register.allow` / `upload.max_mb`）。
- **第一个管理员**必须走命令行（管理端接口都要求 `role='admin'`，没人能给自己提权）：

  ```bash
  cd backend
  .venv\Scripts\python scripts\create_admin.py --username admin --email admin@example.com --password Admin1234!
  # 或把已有用户提升为管理员：
  .venv\Scripts\python scripts\create_admin.py --promote zhangsan
  ```

- 测试库：每个测试用例在事务中执行并回滚（`pytest` fixture 提供 `AsyncSession`，`async with engine.connect()` + 外层事务）。
- 需要一个测试用户 fixture（`test_user` / `Test1234!`）与管理员 fixture（`admin_user` / `admin_headers`），供 `tests/api/*` 复用。

---

## 9. 与 `docs/api.md` 的字段对照检查（提交前必做）

- [ ] `api.md` 里出现的每个响应字段，都能在本文件找到对应列或明确说明它是计算字段（如 `progress`、`accuracy`、`excerpt`、`stale`）。
- [ ] `api.md` 里新增的枚举值，同步更新本文件的 `CHECK` 约束。
- [ ] 本文件新增/改名的列，同步更新 `api.md` 的响应示例。
- [ ] 软删除表新增后，确认所有查询路径都带 `deleted_at IS NULL`。
