# 智能学习系统 · 架构与协作约定

> 本文件面向 AI 编码助手（也供自己查阅），说明本项目的**架构边界、分层规则、约定与红线**。
> 项目：基于大语言模型的智能学习系统（本科毕业设计）｜更新：2026-10-18

---

## 0. 本文件的地位与冲突处理

**优先级（从高到低）：**

```text
docs/api.md  docs/db.md  docs/agent-tools.md      ← 契约，唯一真理
              ↓
          本文档（架构与协作约定）
              ↓
     AI 助手的一般习惯与默认写法
```

- 本文档与契约文档冲突时，**以契约文档为准**，并把本文档改过来。
- 契约文档没有覆盖的细节，按本文档的约定办。
- 两者都没有规定的，**先问，不要自行发明约定**。

**动手任何功能前，先做三件事：**

```text
1. 读 docs/api.md 里对应的接口章节
2. 读 docs/db.md 里对应的表结构
3. 涉及 AI 的，读 docs/agent-tools.md 里的工具与结构化输出定义
```

---

## 1. 项目概述

一个面向个人学习的 Web 系统：用户上传学习资料（PDF / Word）、做笔记、定学习计划与每日任务、记录学习时长，并借助大语言模型完成**问答、资料总结、测试题生成、学习建议**，最后用图表展示学习数据。另有管理员端负责用户、内容、用量与配置管理。

**功能编号（论文与接口注释统一使用这套编号）**

| 编号 | 功能 | 编号 | 功能 |
|---|---|---|---|
| 1 | 用户注册登录 | 8 | AI 学习资料总结 |
| 2 | 个人信息管理 | 9 | AI 学习测试生成 |
| 3 | 学习资料管理 | 10 | 个性化学习推荐 |
| 4 | 在线笔记管理 | 11 | 学习数据统计分析 |
| 5 | 学习计划管理 | 12 | 学习记录管理 |
| 6 | 学习任务管理 | **13** | **管理员端**（13.1 仪表盘 / 13.2 用户 / 13.3 内容 / 13.4 AI 用量 / 13.5 配置与审计） |
| 7 | AI 智能问答 | | |

**主流程**

```text
注册登录 → 上传资料 → 解析正文
    → 加入学习计划 → 生成每日任务 → 完成任务（记学习时长）
    → AI 总结 / AI 出题 → 答题判分 → 统计图表
    → AI 依据统计数据给出学习建议
```

**AI 的四个场景**（全部由 `app/ai/` 承担，见 §5.4）

```text
qa       资料问答（SSE 流式）
summary  资料总结（结构化输出）
quiz     测试题生成（结构化输出）
advice   学习建议（结构化输出）
```

---

## 2. 工程目录结构

```text
smart-learning-system/
├── CLAUDE.md           ← 本文件（架构与协作约定）
├── README.md           ← 启动方式、演示步骤
├── docs/               ← 契约与设计文档，代码的上游
│   ├── 技术栈定稿.md
│   ├── api.md              ← 接口契约
│   ├── db.md               ← 数据库设计
│   ├── agent-tools.md      ← AI 工具与结构化输出契约
│   └── dev-notes.md        ← 版本锁定、能力探针、踩坑记录
├── deploy/
│   └── docker-compose.yml  ← PG + 后端 + 前端
├── backend/
│   ├── app/                ← 见 §5.1 分层
│   ├── alembic/            ← 迁移脚本
│   ├── storage/            ← 上传文件（不入 Git）
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/                ← 见 §5.3 分层
    ├── package.json
    └── .env.example
```

**三个工程单元的边界**

| 单元 | 负责 | 不负责 |
|---|---|---|
| `backend/app` | 业务规则、权限校验、数据持久化、AI 编排、文件落盘 | 页面渲染 |
| `frontend/src` | 页面、交互、状态、展示、调接口 | 任何业务规则、积分式计算、权限判定、模型密钥 |
| `docs/` | 契约与设计 | — |

> **后端只有一个进程。** AI 能力在 `backend/app/ai/` 内，是同一个 FastAPI 应用的一部分，**不拆成独立的 AI 微服务**（`docs/技术栈定稿.md` §10）。这是本项目与「前端 + 业务后端 + AI 服务」三体架构的根本区别。

---

## 3. 整体架构

```text
                      浏览器
                        │
                        ↓
          ┌─────────────────────────────┐
          │  frontend/  React 19 + antd │
          │  用户端 /admin 管理端        │
          └──────────────┬──────────────┘
                         │ HTTP（/api/v1）· SSE（问答流式）
                         ↓
          ┌─────────────────────────────┐
          │  backend/  FastAPI 单进程    │
          │  api → services → models     │
          │            ai/（create_agent）│
          └───┬──────────────┬──────────┘
              │              │ HTTPS
       asyncpg│              ↓
              ↓        大模型 API（OpenAI 兼容）
        ┌───────────┐
        │ PostgreSQL│  business data
        └───────────┘
```

**原则**

```text
前端 → FastAPI → 数据库 / 大模型
```

- **不能绕过 FastAPI。** 前端不直连数据库，也不直连大模型（密钥只在后端环境变量里）。
- SSE 流式回答也走 FastAPI 中转，不把模型地址暴露给浏览器。

---

## 4. 身份与权限体系

**唯一体系：自研双角色 + SQL 层归属过滤。不要引入第二套。**

```text
app_user.role ∈ { user, admin }
        ↓
Depends(get_current_user)   用户端依赖
Depends(get_current_admin)  管理端依赖
```

**规则**

| 规则 | 说明 |
|---|---|
| 角色读库判定 | JWT 只带 `sub` / `pv` / `exp`；每次鉴权按 `sub` 读库取 `role` 与 `is_active`，**不信任 token 里的角色声明** |
| 归属过滤写在 SQL 里 | 每条查询都必须带 `user_id = current_user.id`，**不是查出来再判断** |
| 用户端越权 → 404 | 不返回 403，避免通过状态码枚举「别人的资源存在」 |
| 管理端角色不足 → 403 | `AUTH_004`；账号被禁用 → 403 `USER_003` |
| 管理员不能操作自己 | 禁用 / 降级 / 重置密码 / 强制下线自己 → 400 `ADMIN_001` |
| 失效机制唯一 | 改密码 / 改角色 / 强制下线，一律 `token_version + 1`，不额外引入黑名单 |
| 前端只做显示控制 | 隐藏菜单或按钮**不等于**权限控制；真正的校验只在依赖里 |

**明确禁止**

```text
引入第三方权限框架（Casbin / FastAPI-Users / Keycloak / Authlib 权限组件）
自建权限点、权限组、菜单表、部门表
在前端做「是不是管理员」的业务判断并据此调用管理端接口
```

管理员端的菜单显示只是 UI 便利；即使前端被绕过，后端也必须拒绝。

---

## 5. 分层与依赖方向

### 5.1 后端分层（`backend/app/`）

| 层 | 包 | 职责 | 允许依赖 |
|---|---|---|---|
| 入口 | `app/main.py` | 创建应用、中间件、异常处理、挂载路由 | 下层全部 |
| 配置 | `app/core/` | `config.py` 设置、`security.py` 哈希与 JWT、`deps.py` 依赖、`exceptions.py` 业务异常、`logging.py` | 无 |
| 数据 | `app/db/` | `engine.py` 引擎、`session.py` 会话工厂 | `core` |
| 模型 | `app/models/` | SQLModel `table=True` 表模型 | `db` |
| 校验 | `app/schemas/` | 请求 / 响应 Pydantic 模型 | `models` |
| 接口 | `app/api/v1/` | 路由、依赖注入、状态码、序列化；**只做编排** | `schemas`、`services`、`ai`、`core` |
| 业务 | `app/services/` | 业务规则、事务、聚合查询；**不依赖 Request** | `models`、`schemas`、`core` |
| AI | `app/ai/` | `llm.py` 模型、`agents.py` Agent 工厂、`tools/` 只读工具、`prompts/` 提示词、`schemas.py` 结构化输出、`usage.py` 用量 | `services`、`core` |
| 工具 | `app/utils/` | 文档解析、文本清洗、文件读写 | 无 |

**依赖方向（只能向下，反向不存在）**

```text
api/v1
  ├── services ──→ models ──→ db
  ├── ai ────────→ services
  ├── schemas
  └── core

utils  ← 被 services 与 ai 复用（不与数据库耦合）
```

**硬约束**

```text
services 里不得出现 FastAPI 的 Request / Depends / HTTPException → 用自定义异常
services 里不得拼 HTTP 响应、不得设置状态码
api 层不得直接写 SQL、不得直接操作 session 做业务规则
ai/tools 里不得写库（见 §5.4）
utils 里不得 import services（避免环）
```

### 5.2 前端分层（`frontend/src/`）

| 层 | 目录 | 职责 |
|---|---|---|
| 网络 | `api/` | 一个 axios 实例 + 按模块的请求函数；拦截器注入 token、处理 401 刷新 |
| 类型 | `types/` | `openapi-typescript` 生成 + 手写扩展（错误码、SSE 事件） |
| 服务端状态 | TanStack Query | **所有列表与详情数据**；负责缓存、失效、重试 |
| 客户端状态 | `stores/` | **只放** access token、当前用户、UI 偏好 |
| 路由 | `router/` | `RequireAuth` / `RequireRole` 守卫、懒加载 |
| 页面 | `pages/` | 按功能域分目录；管理端在 `pages/admin/`（独立 chunk） |
| 组件 | `components/` | 通用：上传器、Markdown 渲染、图表卡片、空状态 |
| 钩子 | `hooks/` | `useAuth`、`usePagination`、`useSSE` |

**硬约束**

```text
业务数据不得放进 Zustand（除登录态外）
组件之间不得用 Context 传业务数据
不得自己写 fetch 缓存或 loading 状态机 —— 交给 TanStack Query
字段名不做 camelCase 转换，全链路 snake_case
```

### 5.3 AI 层铁律

| # | 铁律 |
|---|---|
| 1 | **工具只读，绝不写库**；所有写操作由 `services` 在拿到 Agent 结果后执行 |
| 2 | **`user_id` 不作为工具参数**，用工厂闭包绑定当前用户 |
| 3 | 单次工具返回 ≤ 4000 字符，长文档用 `offset` / `limit` 分片 |
| 4 | 工具内部不抛异常，返回 `{"ok": false, "error": ...}` |
| 5 | 所有模型调用必须收敛在 `app/ai/`，其他层不得直接 import 厂商 SDK |
| 6 | 结构化输出必须先过 Pydantic，再过业务二次校验器，才能落库 |
| 7 | 一次 Agent 调用写一行 `ai_usage`，token 需在**多轮 `AIMessage` 上累加** |

> 详细定义见 `docs/agent-tools.md`。工具与 `api` 层共用同一个 service 函数，**不允许各写一份**。

---

## 6. 数据库约定

**核心表（14 张）**

```text
app_user  material  note  study_plan  study_task  study_record
chat_session  chat_message  quiz  quiz_attempt
ai_generation  ai_usage  app_setting  admin_audit_log
```

**约定**

| 项 | 规则 |
|---|---|
| 主键 | `UUID`，Python 侧 `default_factory=uuid4` |
| 时间 | `TIMESTAMPTZ`，统一存 UTC；「今天」按 `APP_TIMEZONE`（默认 `Asia/Shanghai`）算 |
| 枚举 | `VARCHAR` + `CHECK`，**不用 PG 原生 `ENUM`** |
| 软删除 | `deleted_at`，查询一律带 `deleted_at IS NULL` |
| 唯一约束 + 软删除 | 必须用**部分唯一索引**（`postgresql_where`），否则删了就无法重建 |
| 大字段 | `extracted_text` 等不进任何列表响应 |
| 统计 | 不设冗余统计列，一律聚合查询；图表数据缺日补零 |
| 中文搜索 | `ILIKE` + `pg_trgm`（`gin_trgm_ops`），**不用 `to_tsvector`** |
| 迁移 | `alembic revision --autogenerate` 后必须人工审阅；`env.py` 只 import `models` 包；特殊列（`JSONB` / `ARRAY` / 部分索引 / `CHECK`）手写 |

**禁止**

```text
在 models 之外新建表（表结构一律先在 docs/db.md 定义）
绕过 Alembic 手改数据库结构
使用 Enum 类型列
对已 upgrade 的迁移文件做修改（要改就新建一个迁移）
```

> 逐字段定义见 `docs/db.md`。

---

## 7. 接口约定

| 项 | 约定 |
|---|---|
| 前缀 | `/api/v1`（管理端 `/api/v1/admin`，健康检查 `/health` 除外） |
| 命名 | 全链路 snake_case |
| 分页 | `?page=1&size=20` → `{items, total, page, size}` |
| 错误体 | `{code, message, detail}`；`message` 是可直接展示的中文文案 |
| 列表瘦身 | 列表不返回大字段（正文、答案、`summary_md`、完整笔记内容） |
| 删除 | 返回 `204`，只软删除 |
| 幂等 | `POST /plans/{id}/generate-tasks` 幂等（部分唯一索引保证） |
| 流式 | 问答走 SSE，事件名固定为 `meta` / `tool` / `delta` / `done` / `error` |
| 文档 | `/docs` 是交付物，接口必须带 `summary` 与示例，答辩时要用 |

**禁止**

```text
自定义一套 `{code: 0, data: ...}` 的包体（错误体已定，成功直接返回资源）
在用户端接口返回 403（越权一律 404）
让列表接口返回全部字段「反正前端不用」
前端用 EventSource 调 POST 流式接口（要用 fetch + ReadableStream）
```

> 逐接口定义见 `docs/api.md`。

---

## 8. 环境与端口

**开发环境**

| 服务 | 地址 | 说明 |
|---|---|---|
| 前端 | `http://localhost:5173` | Vite dev server；`server.proxy` 把 `/api` 转发到 8000（不发 CORS） |
| 后端 | `http://localhost:8000` | Uvicorn `--reload`；文档 `/docs` |
| PostgreSQL | `localhost:5432` | 库名 `smart_learning` |
| 上传目录 | `backend/storage/` | 不入 Git |

**生产 / 演示环境**

```text
docker compose up -d
  前端 nginx :80     后端 :8000     PostgreSQL :5432（仅容器网络内可达）
  后端容器启动时执行 alembic upgrade head
```

> 演示不用云服务器；数据库端口不对宿主机暴露。

**本地开发一键启动**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

会先清掉占用 **8000 / 5173** 的旧进程（含 uvicorn reloader 的孤儿 worker、残留的 vite），再原地启动前后端。
`-Stop` 只停不启；`-BackendOnly` / `-FrontendOnly` 单独起一个。
**改完后端代码或改路由表后，用它重启一次** —— `uvicorn --reload` 与 Vite 的 HMR 在本机都不可靠（见 §11）。

---

## 9. 环境变量与敏感信息

**所有配置只从环境变量读**（`app/core/config.py` 的 `Settings`），后端 `.env`、前端 `.env` 都不入 Git，只提交 `.env.example`。

| 用途 | 环境变量 |
|---|---|
| 应用密钥（JWT） | `SECRET_KEY` |
| 数据库 | `DATABASE_URL` |
| 大模型 | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` |
| 上传 | `UPLOAD_DIR`、`MAX_UPLOAD_MB` |
| AI 行为 | `LLM_MAX_INPUT_CHARS`、`LLM_MAX_STEPS`、`AI_AGENT_TIMEOUT`、`AI_DAILY_QUOTA`、`AI_USE_DEEP_AGENT` |
| 前端 | `VITE_API_BASE_URL` |

**禁止**

```text
把 API Key / 数据库密码写进任何 .py / .ts / .tsx 源码或注释
把任何 Secret 放进前端代码或前端环境变量
在日志、异常响应、Swagger 示例里回显密钥
把真实 .env 提交到 Git
```

> 运行时可调的项（AI 开关、每日配额、是否开放注册）走 `app_setting` 表，**不走 `.env`**；改模型必须走 `.env` + 重启。

---

## 10. 命名规范

| 对象 | 规范 | 示例 |
|---|---|---|
| 数据表 | 单数 snake_case | `study_task` |
| 字段 | snake_case | `plan_date` |
| 接口路径 | 复数资源 + 短横线层级 | `/api/v1/study-records` |
| Python 模块 | snake_case | `material_service.py` |
| Python 函数 / 变量 | snake_case | `read_text_chunk` |
| Python 类 | PascalCase | `QuizOut`、`StudyTask` |
| Pydantic 响应模型 | `XxxOut` / `XxxCreate` / `XxxUpdate` | `SummaryOut`、`NoteCreate` |
| 常量 / 枚举值 | 大写常量、小写枚举值 | `AI_SCENES`, `scene="quiz"` |
| React 组件 | PascalCase 文件与组件名 | `MaterialList.tsx` |
| React 钩子 | `useXxx` | `useSSE.ts` |
| 前端请求函数 | 动词 + 资源 | `createMaterial()` |

---

## 11. 编码规范与已知坑

**规范**

```text
注释写中文，解释「为什么」而不是「做了什么」
函数保持单一职责，service 函数 ≤ 60 行，超了就拆
不做花哨抽象（一层接口一层实现的写法在毕设里是负分）
不留 TODO / 注释掉的死代码 / 调试 print / 假数据
不为了跑通界面而在业务代码里写死 mock 数据（演示数据用测试 fixture 或手工录入）
```

**必须避开的坑（都真会踩）**

| 坑 | 规避 |
|---|---|
| `MissingGreenlet` | 不混用同步/异步 Session；关系用 `selectinload` 或 `lazy="selectin"`；`expire_on_commit=False` |
| Alembic 漏表 | `alembic/env.py` 只 import `models` 包；每次迁移人工 diff |
| `alembic` 报 `UnicodeDecodeError` | `alembic.ini` **必须纯 ASCII**（configparser 按系统 locale 编码读，中文 Windows 是 GBK） |
| 校验路由取不到子路由 | FastAPI 0.143 把 `include_router` 的子路由包成 `_IncludedRouter`，**不要遍历 `app.routes`**；用 `app.openapi()["paths"]` 或 httpx 实测 |
| Vite 代理 `ECONNREFUSED` | 代理目标写 `http://127.0.0.1:8000`，不要写 `localhost`（Windows 可能先解析到 IPv6 `::1`） |
| ruff 对中文注释报 `RUF001/2/3` | 已在 `backend/pyproject.toml` 里 ignore 这三条；注释照常用中文 |
| antd 6 组件 API 变更 | `Alert.message` 已改名 `title`（旧名会打废弃警告）；`List` 已废弃，替代品 `Listy` 是**虚拟滚动列表**（`@rc-component/listy`）。业务列表一律用 `Table`，静态文案用原生标签 |
| Windows PowerShell 脚本乱码/语法报错 | `.ps1` **必须 ASCII-only 或带 UTF-8 BOM**：PowerShell 5.1 对无 BOM 文件按系统 ANSI（GBK）解码，中文会吃掉换行符并破坏解析 |
| `wsl --install` 返回码 1 却不报错 | 该命令需要管理员权限，非提权 shell 会静默失败；必须在**管理员终端**里执行 |
| `docker` 命令找不到 / `docker-credential-desktop` not found | 终端从**安装前启动的 explorer.exe** 继承旧 PATH。`deploy/setup-db.ps1` 会把 docker 目录前插到当前会话 PATH 自愈；永久修复需重启资源管理器或注销重登 |
| 拉镜像超时 `dialing registry-1.docker.io:443` | Docker Hub 国内不可直连；在 `~/.docker/daemon.json` 配 `registry-mirrors` 后 `docker desktop restart`（改配置要合并原键，别整覆盖） |
| 容器起不来且日志报 `there appears to be PostgreSQL data in: /var/lib/postgresql/data` | **PG18 官方镜像数据目录布局变更**：18 起必须挂 `/var/lib/postgresql`，挂旧路径会被判为升级残留而拒绝启动 |
| 本机连 Docker 里的 PG「不需要密码」 | 官方镜像 `pg_hba.conf` 对本机（localhost）是 `trust`，`POSTGRES_PASSWORD` 也只在首次初始化时生效。别用「改密码后仍能连」判断配置没生效；生产需 `POSTGRES_HOST_AUTH_METHOD=scram-sha-256` + 不暴露端口（详见 `docs/db.md` §1.1） |
| Swagger 文档里的 422 与实际返回不一致 | FastAPI 自动生成 422 时用的是框架默认体 `{"detail": [...]}`，而我们的契约是 `{code, message, detail}` | 在 `main.py` 的 `include_router(..., responses={422: {"model": ErrorOut}})` 覆盖；新增路由不要再单独声明 422 |
| **multipart 中文文件名变乱码（只剩 `_`）** | HTTP 头按 latin-1 解码，而浏览器/httpx 发的是**原始 UTF-8 字节** | `files.fix_filename_encoding` 做一次 latin-1→utf-8 可逆还原；清洗只去路径分隔符与控制字符，**不要把所有非 ASCII 换成下划线** |
| `uvicorn --reload` 改代码不生效，且留下孤儿 worker 占端口 | Windows 上 reloader 用 multiprocessing spawn：父进程被杀后子进程继续持有端口并跑旧代码 | 用 `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 找 CommandLine 含 uvicorn 的进程杀掉；**本机开发建议不用 `--reload`**，改完手动重启 |
| 改了路由表/常量后前端没生效 | Vite 只能 Fast Refresh 组件，对 `export const router` 这类导出会 `hmr invalidate`；旧 dev server 还会继续返回缓存模块 | 用 `scripts/dev.ps1` 重启（会先清端口），**不要只刷新页面** |
| `ZoneInfo('Asia/Shanghai')` 报 `ZoneInfoNotFoundError` | Windows 与 alpine 镜像都**没有系统 IANA 时区库**，Python 的 zoneinfo 需要 PyPI 的 `tzdata` | 已把 `tzdata` 加进 `requirements.txt`；凡是用到 `APP_TIMEZONE` 的地方都依赖它 |
| `PATCH /plans` 传日期被静默忽略 | Pydantic 默认忽略未声明的字段，接口返回 200 但日期没变，和契约「返回 400」不符 | `PlanUpdate` 里显式声明 `start_date`/`end_date`，由 service 检测到就抛 400 —— **要拒绝某个字段时，必须先声明它** |
| 工具包内 `from app.ai.tools import MAX_TOOL_CHARS` 报循环导入 | `tools/__init__.py` 既导出工具函数，又要给子模块提供常量 | 常量单独放 `app/ai/tools/constants.py` |
| 用 PowerShell here-string 往 Python 传中文会写成 `?` | 管道编码是 ANSI/GBK，多字节字符被替换成 `?`（症状：文件里出现 `"B ??"`） | 改中文内容一律用编辑工具；shell 脚本只做 ASCII 替换。**写完要 grep 一遍 `??` 确认** |
| 没配 `LLM_API_KEY` 时接口应当 503 而不是 500 | `ChatOpenAI` 需要非空 api_key，直接构造会抛校验异常 | `app/ai/llm.py` 先检查 key，缺失抛 `AiNotConfigured`(503 `SYS_503`)；探针脚本也先检查再跑 |
| antd 6 还有其它组件改名 | `Drawer.width`→`size`、`Space.direction`→`orientation`（之前还有 `Alert.message`→`title`、`List`→`Listy`） | 以控制台警告为准逐个改；**每次改完页面都要看控制台，不要只看能不能渲染** |
| 部分唯一索引没生成 | autogenerate 不生成 `postgresql_where`，手写 |
| Agent 超时不生效 | `ChatOpenAI(timeout=)` 只管单次请求，要用 `asyncio.wait_for` 包住整轮 |
| token 统计偏小 | 遍历所有 `AIMessage` 累加 `usage_metadata`，不能只取最后一条 |
| 东八区取错日期 | 「今天」统一用 `APP_TIMEZONE` 计算，不用 `date.today()` |
| LIKE 通配注入 | 关键词里的 `%` `_` 转义后再拼 `ILIKE` |
| React 全树重渲染 | 列表数据放 TanStack Query，不放 Context / Zustand |
| 401 刷新风暴 | 刷新令牌用单例 Promise，并发请求共享同一次刷新 |
| N+1 查询 | 管理端用户列表的 `counts` 用一条聚合子查询 |

---

## 12. 开发原则

项目是毕业设计，目标是：

```text
能跑通 → 功能完整 → 结构清晰 → 方便演示 → 方便答辩
```

优先级：

```text
功能正确
  > 业务闭环
    > 代码清晰
      > 契约与文档一致
        > 可维护
          > 技术亮点
            > 性能优化
```

**不要为了显得高级而把架构做复杂。** 评委关心的是「功能是否真的能用、数据是否真的存下来了、AI 是否真的接进去了」，不是设计模式的层数。

**每个功能的完成定义（Definition of Done）**

```text
1. 契约文档里已有它的接口与表结构
2. 接口在 /docs 里能跑通（Swagger 手测过）
3. 前端能真实调用并展示（不是假数据）
4. 有一条 pytest 用例覆盖主路径 + 一条越权用例
5. 跨用户不可见（用两个测试账号验证过）
6. 在 docs/dev-notes.md 里没有遗留未记录的坑
```

---

## 13. 不要擅自引入

没有明确要求，**不要**主动引入：

```text
微服务 / 拆分 AI 服务
消息队列、Celery、定时任务框架
Redis 或其他缓存（配额与去重先用 PostgreSQL）
向量数据库 / RAG / pgvector（列为论文展望，不进实现）
GraphQL / gRPC / WebSocket（问答用 SSE 已够）
Next.js / SSR / 移动端
第三方权限框架（见 §4）
第二个 ORM 或查询构建器
新的 UI 组件库（已定 antd 6）
状态管理库的替代品（Redux / MobX / Jotai）
Docker Compose 之外的编排工具
```

**加任何新依赖前必须交代**：现有库为什么做不了、包名与版本、是否影响启动体积、是否需要在 `requirements.txt` / `package.json` 与 `docs/技术栈定稿.md` 里登记。**顺手加依赖视为错误。**

---

## 14. 修改代码前的工作流

```text
1. 看 docs/ 里的对应契约（api.md / db.md / agent-tools.md）
2. 看当前目录与相关代码，搜索是否已有类似实现
3. 看当前配置（.env.example、requirements.txt、package.json）
4. 确认要改的层（api / service / model / ai / 前端）与依赖方向是否合法
5. 制定最小修改方案 → 说明 → 再动手
```

**偏好顺序**

```text
复用  >  修改  >  新增  >  重构
```

不要拿到一个需求就批量创建文件。一次只推进一个功能模块，做完跑测试、提交 Git，再进入下一个。

### 14.1 提方案时必须交代的五件事

只要方案涉及后端或 AI，就不能只说「加一个接口」「写个 service 方法」「让 AI 生成一下」。方案里必须先写清：

```text
1. 新增 / 修改哪些文件 —— 完整路径 + 一句话职责
2. 落在哪一层 —— api / schema / model / service / ai 工具 / 前端页面
3. 调用链 —— 谁调谁，层次画出来
4. 被谁复用 —— 哪个接口进来、是否被 agent 工具复用、被哪个测试覆盖
5. 是否需要改契约 —— api.md / db.md / agent-tools.md 改哪一节
```

**粒度参考（照这个粒度说，别更粗）**

```text
新增：backend/app/services/material_service.py 里的
      read_text_chunk(db, user_id, material_id, offset, limit) -> TextChunk

分层：service 层，只接收 db 与参数，不依赖 Request
调用链：api/v1/materials.py  GET /api/v1/materials/{id}/text
             ↓
        material_service.read_text_chunk
             ↑
        ai/tools/materials.py  make_read_material_chunk（契约要求复用同一个函数，不另写一份）

被谁复用：资料详情页正文预览、summary / quiz 两个 Agent 场景的读文档工具
契约：返回结构已在 docs/api.md §5；截断 4000 已在 docs/agent-tools.md §3.3
测试：tests/services/test_material_service.py、tests/api/test_materials.py（含越权用例）
风险：需确认 offset 越界返回空文本而不是报错
```

**改动已有代码时，还要额外说明**：改的是哪个函数、为什么不能只加新函数、会影响哪些现有调用方。

> 不写文件路径与层级的方案，等于没方案。

---

## 15. 禁止的危险操作

未经明确要求，不要：

```text
git reset --hard / git clean -fd / git push --force
删除或覆盖未提交的代码（尤其是自己没读过的文件）
批量删除文件
修改已 upgrade 的迁移文件
直接改数据库结构（必须走迁移）
对生产/演示库执行 DELETE / UPDATE / DROP
把 .env 或 storage/ 提交进 Git
```

不确定时停下来问，不要「先做了再说」。

---

## 16. 完成任务后的汇报格式

```text
本次修改：
1. 修改了什么（文件 + 一句话）
2. 新增了什么
3. 复用了哪些已有代码
4. 是否改了契约文档（改了哪一节）
5. 如何验证（命令 / 步骤）
6. 已知问题或未做的部分
```

保持简洁，不要贴大段代码。

---

## 17. 里程碑与当前进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | 环境骨架：FastAPI `/health`、Vite+React、PG(Docker)、Alembic 首个迁移（含 `pg_trgm`）、pytest 冒烟 | ✅ **已完成** —— 全部验收项通过；`/health` → 200 `{status:ok, db:ok}`；`4 passed` |
| M1 | 注册登录 / 刷新 / 个人信息 / 前端守卫 | ✅ **已完成** —— 41 个后端用例；浏览器端到端（注册→登录→刷新保持→改资料→登出）全部通过 |
| M2 | 资料上传 + 解析 + 鉴权下载 | ✅ **已完成** —— 74→81 个后端用例；真实 DOCX/PDF 上传→解析→分片→下载全通；中文文件名已修 |
| M3 | 笔记 CRUD + 搜索分页 | ✅ **已完成** —— 95 个后端用例；浏览器新建/保存/列表闭环；列表不返回正文 |
| M4 | 学习计划 + 每日任务 + 学习记录 | ✅ **已完成** —— 130 个后端用例；计划→生成任务→完成→写记录全链路；删任务后可补生成 |
| M5 | AI 层：能力探针 → qa / summary / quiz / advice + 用量配额 | ✅ **已完成** —— 169 个后端用例；探针 3/3 PASS；真实模型跑通总结/出题/判分/建议/问答（含工具调用与 SSE 流式）；前端 `/ai` 四个 Tab 浏览器实测通过 |
| M6 | 推荐 + 统计图表 + 全局异常 | ✅ **已完成** —— 185 个后端用例；§12 契约补齐（含功能 10 推荐）；`/stats` 四个统计接口 + `/recommendations` 规则推荐；前端统计页（ECharts）与工作台改造；浏览器实测通过 |
| M6b | **功能 13** 管理员端 5 个子模块 + `/admin` 前端 | 未开始 |
| M7 | 测试、Docker 部署、截图、论文材料 | 未开始 |

> 每完成一个里程碑，在此表更新状态，并在 `docs/dev-notes.md` 记录实际耗时与踩坑。

---

## 18. 最终原则

```text
先读契约，再写代码。
先看现有实现，再新增文件。
先复用，再重写。

权限只有一套，校验只在后端。
AI 只读工具，写库只走 service。
契约改了才改代码，不是反过来。

先保证功能正确，再谈技术亮点。
不为了复杂而复杂。
```
