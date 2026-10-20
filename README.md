# 智能学习系统（smart-learning-system）

基于大语言模型的智能学习系统 · 本科毕业设计。

用户上传学习资料（PDF / Word）、做笔记、制定学习计划与每日任务、记录学习时长，并借助大语言模型完成
**资料问答、资料总结、测试题生成、学习建议**，最后以图表展示学习数据；另有管理员端负责用户、内容、AI 用量与系统配置管理。

---

## 技术栈速览

| 层 | 选型 |
|---|---|
| 前端 | React 19 + TypeScript + Vite 8 + Ant Design 6 + TanStack Query + Zustand + ECharts |
| 后端 | Python 3.12 + FastAPI + SQLModel（异步）+ Alembic |
| 数据库 | PostgreSQL 18 |
| AI | LangChain 1.x `create_agent`（工具只读 + 结构化输出） |
| 认证 | OAuth2 Password Bearer + JWT + pwdlib(Argon2) |

完整选型与版本基线见 [`docs/技术栈定稿.md`](docs/技术栈定稿.md)。

---

## 目录结构

```text
├── CLAUDE.md            架构与协作约定（分层、依赖方向、红线）
├── docs/                契约与设计（代码的上游）
│   ├── 技术栈定稿.md
│   ├── api.md               接口契约
│   ├── db.md                数据库设计
│   ├── agent-tools.md       AI 工具与结构化输出契约
│   └── dev-notes.md         版本锁定、能力探针、踩坑记录
├── deploy/docker-compose.yml
├── backend/             FastAPI 应用、迁移、测试
└── frontend/            React 应用
```

---

## 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.12+ | 后端 |
| Node.js | 22+ | 前端（Vite 8 要求） |
| PostgreSQL | 16+（推荐 18） | 数据库；也可用 Docker 启动 |

---

## 快速开始

> **本地开发一键启动（推荐）**：`powershell -ExecutionPolicy Bypass -File scripts\dev.ps1`
> 会先清掉占用 8000/5173 的旧进程，再启动前后端；改了后端代码或路由表后也用它重启。

### 1. 数据库

**方式 A：Docker（推荐，需先有 Docker Desktop）**

一条命令完成「起容器 → 等健康 → 跑迁移 → 校验连通」：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\setup-db.ps1
```

只想手动分步执行的话：

```bash
docker compose -f deploy/docker-compose.yml up -d
cd backend && alembic upgrade head
```

> **国内网络与常见坑（本机实测踩过，均已规避）**
>
> | 现象 | 原因与处理 |
> |---|---|
> | `docker` 命令找不到 / `docker-credential-desktop` not found | 终端从**安装 Docker 之前启动的** `explorer.exe` 继承了旧 PATH。`setup-db.ps1` 会自动把 docker 目录加入当前会话自愈；永久修复：重启资源管理器或注销重登 |
> | 拉镜像超时 `dialing registry-1.docker.io:443` | Docker Hub 国内不可直连。在 `~/.docker/daemon.json` 里加 `registry-mirrors`（实测可用：`docker.m.daocloud.io`、`docker.1ms.run`、`docker.xuanyuan.me`、`docker.1panel.live`），然后 `docker desktop restart`。**改这个文件要合并原有键**（如 `builder.gc`），不要整文件覆盖 |
> | 容器健康检查不过，日志报 `there appears to be PostgreSQL data in: /var/lib/postgresql/data` | **PostgreSQL 18 镜像变更了数据目录布局**：18 起必须挂载 `/var/lib/postgresql`。`deploy/docker-compose.yml` 已按新布局配置；若你改用其他版本镜像或旧教程的 `/var/lib/postgresql/data`，就会踩这个坑 |

> **Windows 首次安装 Docker Desktop 的前置（本机实测需要）**
> Docker Desktop 依赖 WSL2，而 WSL2 需要**管理员权限 + 重启**，无法由脚本静默完成：
>
> ```powershell
> # 1) 以【管理员身份】打开 PowerShell（Win+X → 终端(管理员)），执行：
> wsl --install --no-distribution
>
> # 2) 重启电脑（必须）
>
> # 3) 重启后在普通终端安装并启动 Docker Desktop：
> winget install -e --id Docker.DockerDesktop
> #    首次启动若提示启用 WSL 集成，按默认同意即可
>
> # 4) 托盘图标变为「运行中」后，回到仓库根目录：
> powershell -ExecutionPolicy Bypass -File deploy\setup-db.ps1
> ```
>
> 若不想装 Docker，直接用下面的方式 B 更省事（无需 WSL、无需重启）。

**方式 B：本机已安装 PostgreSQL**

用 psql 或任意客户端以**超级用户**连接后执行一次：

```sql
CREATE USER app WITH PASSWORD 'app';
CREATE DATABASE smart_learning OWNER app;
```

> `pg_trgm` 自 PostgreSQL 13 起是 *trusted* 扩展，库属主即可创建，
> 所以迁移里的 `CREATE EXTENSION IF NOT EXISTS pg_trgm` 用 `app` 账号就能执行，无需额外的超级用户操作。

### 2. 后端

```bash
cd backend

python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt      # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt   # macOS / Linux

copy .env.example .env                                           # 生成配置文件（.env 不入 Git）
# 编辑 .env：把 SECRET_KEY 换成随机值
python -c "import secrets; print(secrets.token_urlsafe(48))"

.venv\Scripts\python -m alembic upgrade head                     # 建表 + 创建 pg_trgm 扩展
.venv\Scripts\python -m uvicorn app.main:app --reload            # http://localhost:8000
```

接口文档：<http://localhost:8000/docs>

### 3. 前端

```bash
cd frontend
npm install
npm run dev                                                      # http://localhost:5173
```

打开 <http://localhost:5173> 会进入工作台（「今天做什么」推荐 + 今日任务 + 近 7 天概览）。
（开发期前端只访问同源路径，由 Vite 代理转发到 8000 端口，不产生跨域。）

主要页面：`/` 工作台 · `/materials` 学习资料 · `/notes` 在线笔记 · `/plans` 计划/任务/记录 ·
`/ai` AI 助手（问答 / 总结 / 测试题 / 建议）· `/stats` 学习统计图表 · `/profile` 个人信息 ·
`/admin/*` 管理端（功能 13，仅管理员可见：仪表盘 / 用户 / 内容 / AI 用量 / 配置与审计）。

**第一个管理员**（管理端不能给自己提权，必须走命令行）：

```bash
cd backend
.venv\Scripts\python scripts\create_admin.py --username admin --email admin@example.com --password Admin1234!
# 或把已有用户提升为管理员：--promote <username>
```

---

## 一键部署（Docker Compose，M7）

把 PostgreSQL + 后端 + 前端（nginx 反代）打包成一键起：

```bash
# 1) 准备敏感配置（不入库）
copy deploy\.env.example deploy\.env
#    编辑 deploy\.env：填 LLM_API_KEY（不填也能起，只是 AI 接口 503）

# 2) 构建并启动全套
docker compose -f deploy/docker-compose.yml up -d --build

# 3) 访问
#    前端  http://127.0.0.1:8080
#    后端  http://127.0.0.1:8000/health  （应返回 {status:ok, db:ok}）
```

- 后端容器启动时自动 `alembic upgrade head`；上传文件用 `uploads` 卷持久化。
- 创建第一个管理员（管理端不能给自己提权）：

  ```bash
  docker exec -it sls-backend python scripts/create_admin.py --username admin --email a@b.c --password xxx
  ```

> 本地开发仍用 `scripts\dev.ps1`（前后端热启动）；Docker 是**交付/演示**形态。

---

## 测试

```bash
# 后端：无需数据库也能跑（数据库相关用例会自动 skip）
cd backend
.venv\Scripts\python -m pytest

# 仅跑需要真实数据库/外部服务的用例
.venv\Scripts\python -m pytest -m integration

# 后端静态检查（从仓库根目录或 backend/ 都可以）
.venv\Scripts\python -m ruff check .

# 前端：类型检查 + 构建
cd frontend
npm run build
```

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | 架构边界、分层与依赖方向、权限体系、开发原则、红线 |
| [`docs/技术栈定稿.md`](docs/技术栈定稿.md) | 技术选型、版本基线、工程约定、里程碑、风险 |
| [`docs/api.md`](docs/api.md) | 接口契约（用户端 + 管理端）、错误码、SSE 事件协议 |
| [`docs/db.md`](docs/db.md) | 14 张表的字段/约束/索引、JSONB 结构、E-R 关系、统计 SQL |
| [`docs/agent-tools.md`](docs/agent-tools.md) | Agent 工具签名、结构化输出模型、Prompt 契约、降级矩阵 |
| [`docs/dev-notes.md`](docs/dev-notes.md) | 版本锁定、能力探针结果、踩坑记录、里程碑实际耗时 |
| [`docs/论文材料.md`](docs/论文材料.md) | 论文素材：架构图、E-R 图、时序图（Mermaid）、测试统计、设计取舍 |

> **约定：契约是代码的上游。** 改接口先改 `docs/api.md`，改表先改 `docs/db.md`，改 AI 能力先改 `docs/agent-tools.md`。

---

## 开发进度

当前阶段：**M7 测试 / Docker 部署 / 论文材料 ✅ 已完成** —— 全部 13 个功能 + 7 个里程碑完成，毕业设计系统交付。

- 后端 227 用例全绿、覆盖率 82%；前端 `tsc` + `vite build` 通过。
- Docker 一键部署实机验证（`docker compose -f deploy/docker-compose.yml up -d --build`）。
- 论文材料见 [`docs/论文材料.md`](docs/论文材料.md)；验收与踩坑见 [`docs/dev-notes.md`](docs/dev-notes.md) §3、§4–§12。
- 界面截图：`scripts/screenshots.mjs`（Playwright，需桌面环境跑一次）。
