# 开发日志（Dev Notes）

> 记录环境版本、验证结论与踩坑。答辩材料「方案可行性验证」的原始依据。
> `docs/agent-tools.md` §11 要求的能力探针结果写在这里。

---

## 1. 环境版本锁定

开发机实测（M0 阶段，2026-10-18）：

| 项 | 计划基线 | 开发机实际 | 说明 |
|---|---|---|---|
| Python | 3.12.x | **3.12.10** | ✅ 一致 |
| Node | 22 LTS | **24.7.0** | ✅ 更高，Vite 8 要求 ≥20.19/22，兼容 |
| npm | — | 11.19.1 | — |
| pip | — | 26.0.1 | — |
| PostgreSQL | 18.x | **未安装** | ⚠️ 阻塞 M0 的数据库环节 |
| Docker | — | **未安装** | ⚠️ 同上 |
| Git | — | 2.33.0 | — |

**源上可见的最新版本（`npm view` / `pip download` 实测，2026-10-18）**

| 包 | 实测最新 | 与文档基线差异 |
|---|---|---|
| fastapi | 0.143.5 | ✅ 一致（0.143.x） |
| react | 19.3.1 | ✅ 一致 |
| vite | 8.3.4 | ✅ 一致 |
| antd | 6.6.6 | ✅ 一致 |
| echarts | 6.1.0 | ✅ 一致 |
| @tanstack/react-query | 5.104.4 | ✅ 一致 |
| email-validator | 2.3.0 | M1 新增依赖（Pydantic `EmailStr` 需要） |
| **react-router** | **8.4.0** | ⚠️ 文档写 7.x，实际主版本已到 8 → 采用 8.x |
| **typescript** | **7.0.2** | ⚠️ 文档写 5.x，实际已到 7 → 采用 7.x（待构建验证） |

> 原则：**首周锁定，之后不升大版本**（技术栈定稿 §7）。
> `react-router` 与 `typescript` 的基线修正会在 M0 构建验证通过后写回 `docs/技术栈定稿.md` §1、§7。

---

## 2. 能力探针（M5 第一天必做，对应 `agent-tools.md` §11）

| # | 检查项 | 通过标准 | 结果 | 日期 | 备注（耗时 / token / 报错） |
|---|---|---|---|---|---|
| 1 | 工具调用 | 模型能发起 tool call 并消费返回值 | ✅ **PASS** | 2026-10-19 | qwen-plus，1.7–2.1 s |
| 2 | 结构化输出 | `response_format=<Pydantic>` 能取到 `structured_response` 且校验通过 | ✅ **PASS** | 2026-10-19 | 5.3 s，返回合法单题（4 选项、答案在选项内） |
| 3 | 流式 | `graph.astream(stream_mode="messages")` 能拿到逐段 token | ✅ **PASS** | 2026-10-19 | 4 个 chunk，0.5 s |

**已实测的供应商对比（答辩可用的「方案可行性验证」材料）**

| 供应商 / 模型 | base_url | 工具调用 | 结构化输出 | 流式 | 结论 |
|---|---|---|---|---|---|
| **通义千问 `qwen-plus`**（DashScope OpenAI 兼容） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | ✅ | ✅ | ✅ | **本项目采用**（已跑通四场景端到端） |
| **智谱 `glm-4-flash`**（bigmodel OpenAI 兼容） | `https://open.bigmodel.cn/api/paas/v4` | ✅ | ✅ | ✅ | **合格备用**（同一套探针三项全 PASS；智谱其他模型提示余额不足） |
| OpenCode Zen `deepseek-v4.1-flash` 等付费模型 | `https://opencode.ai/zen/v1` | ❌ 402 | ❌ | ❌ | `Insufficient account funds`（账户无余额） |
| OpenCode Zen 9 个 `-free` 模型 | 同上 | ❌ 403 | ❌ | ❌ | `FreeTierError`（免费层未开通）；`beam-free` 另有 `RegionError` |
| 机器上的 `OPENAI_API_KEY` | `https://api.openai.com/v1` | ❌ | ❌ | ❌ | 直连不可达（国内网络） |
| 智谱其他模型（`glm-4.5` / `glm-4.5-air` / `glm-4-plus`） | bigmodel | ❌ 429 | ❌ | ❌ | `余额不足或无可用资源包` |

> 说明：Zen 的 `/models` 端点用该 Key 能正常返回 44 个模型（**Key 有效**），
> 但所有 `chat/completions` 都被余额/免费层拦截 —— 所以不是代码问题，是账号额度问题。
> 换供应商只需改 `backend/.env` 的 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`，业务代码零改动
> （这正是把模型调用收敛在 `app/ai/llm.py` 的价值）。

**探针不通过时的备用方案**（`agent-tools.md` §11）：
- 工具调用不通 → 换支持 function calling 的模型。
- 结构化输出不通 → 确认走工具策略；仍失败则降级为「先出 JSON 文本再解析」。
- 流式不通 → 问答接口退回非流式 + 前端骨架屏。

---

## 3. 踩坑记录

| 日期 | 现象 | 根因 | 解决 |
|---|---|---|---|
| 2026-10-18 | `alembic` 任何命令报 `UnicodeDecodeError: 'gbk' codec can't decode byte` | `alembic.ini` 被我加了中文注释；configparser 用**系统 locale 编码**读 ini，中文 Windows 是 GBK | 该文件保持**纯 ASCII**，注释写英文；已加字节级校验（见 `docs/db.md` §7） |
| 2026-10-18 | `ruff --fix` 把 `from alembic import context` 排到 first-party 分组 | `backend/alembic/` 目录与第三方包 `alembic` 同名，ruff 误判为本地模块 | `pyproject.toml` 里显式声明 `known-third-party` 包含 `alembic` |
| 2026-10-18 | ruff 对中文注释报 100+ 个 `RUF001/2/3`（全角标点歧义） | 项目注释统一中文，全角标点是正常写法 | 在 `[tool.ruff.lint] ignore` 中关掉这三条并注明原因 |
| 2026-10-18 | Vite 代理潜在 `ECONNREFUSED`（本地实测未复现，但属已知风险） | Windows 上 `localhost` 可能先解析到 IPv6 `::1`，而后端只监听 `127.0.0.1` | 代理目标显式写 `http://127.0.0.1:8000` |
| 2026-10-18 | 校验路由时 `app.routes` 遍历不到 `/health`，一度以为接口没注册 | FastAPI 0.143 的 `include_router` 把子路由包成 `_IncludedRouter`，不再直接暴露 `APIRoute` | 用 `app.openapi()["paths"]` 或 httpx 实测来校验路由，不要遍历 `app.routes` |
| 2026-10-18 | `curl` 输出中文乱码、`ConvertFrom-Json` 报错 | PowerShell 控制台按 GBK 解码 UTF-8 输出 | 只是显示问题，非程序缺陷；要准确输出可用 `curl.exe -o file` 再读文件 |
| 2026-10-18 | `deploy/setup-db.ps1` 语法检查报「意外的标记 {」 | `.ps1` 用无 BOM 的 UTF-8 保存，PowerShell 5.1 按 GBK 解码，中文多字节序列吃掉换行符 | 脚本改为**纯 ASCII**（英文提示）；已加字节级校验 |
| 2026-10-18 | `docker-compose.yml` 用 `Get-Content` 看像是「注释与 services 粘成一行」 | 同上的显示假象：GBK 解码 UTF-8 时把换行当成多字节的一部分 | 用 UTF-8 感知的读取方式（如编辑器/`Get-Content -Encoding utf8`）复核，文件本体完好 |
| 2026-10-18 | `wsl --install --no-distribution` 返回 1 且无明显错误 | 需要管理员权限，非提权 shell 无法弹 UAC，静默失败 | 改为在**管理员终端**手动执行，见 README「方式 A」前置说明 |
| 2026-10-18 | 浏览器控制台报 antd 废弃警告：`List` 与 `Alert.message` | antd 6 变更：`Alert.message` 改名 `title`；`List` 废弃，替代品 `Listy` 是虚拟滚动组件（基于 `@rc-component/listy`） | 静态清单改原生 `<ol>` 渲染；业务列表统一用 `Table`。顺带包体积 962 → 844 kB（gzip 313 → 276 kB） |
| 2026-10-18 | 用 `app.routes` 校验接口是否注册会漏 | 同 `_IncludedRouter` 一条 | 校验前端是否真的渲染，用浏览器 `wait(condition="text")` + 控制台/网络面板，比读源码可靠 |
| 2026-10-18 | `docker compose up` 报 `exec: "docker-credential-desktop": executable file not found in %PATH%` | 凭据助手确实存在且已在**机器级 PATH**里，但终端是从**重启前启动的 explorer.exe** 继承的旧 PATH（Docker 是在 WSL2 重启之后才装的） | 脚本启动时把 docker 所在目录前插到 `$env:PATH`（自愈）；永久修复：重启资源管理器或注销重登 |
| 2026-10-18 | 拉镜像超时：`dialing registry-1.docker.io:443 ... connection attempt failed` | Docker Hub 在国内不可直连 | 在 `~/.docker/daemon.json` 配 `registry-mirrors`（实测可用：daocloud / 1ms.run / xuanyuan.me / 1panel.live；163 与腾讯云已失效），然后 `docker desktop restart`。改配置时要**合并**原文件的 `builder.gc` 等键，别整覆盖 |
| 2026-10-18 | 容器启动后健康检查一直不过，日志报 `there appears to be PostgreSQL data in: /var/lib/postgresql/data` | **PostgreSQL 18 官方镜像改了数据目录布局**：18 起必须挂 `/var/lib/postgresql`，挂旧的 `/var/lib/postgresql/data` 会被判定为「升级残留」而拒绝启动 | compose 挂载点改为 `pgdata:/var/lib/postgresql`（docker-library/postgres #1259）；同时 `docker compose down -v` 清掉用旧布局初始化的卷 |
| 2026-10-18 | 旧 uvicorn 实例仍在占用 8000，新实例绑定失败 | 前几轮留下的后台进程 | 用 `Get-NetTCPConnection -LocalPort 8000` 找 PID 再 `Stop-Process`；测试前先确认端口归属 |
| 2026-10-19 | autogenerate 出的迁移执行时 `NameError: name 'sqlmodel' is not defined` | SQLModel 的 `AutoString` 被渲染成 `sqlmodel.sql.sqltypes.AutoString(...)`，而迁移文件只 import sqlalchemy | 在 `alembic/env.py` 加 `render_item` 钩子，把 SQLModel 类型统一渲染成 `sa.String(length=N)`；**以后所有迁移都自动干净** |
| 2026-10-19 | 多个用例单独跑通过、一起跑大量 `AttributeError` + `Connection._cancel was never awaited` | pytest-asyncio 默认**每个测试换事件循环**，而 `engine` 是模块级连接池，池中连接属于已结束的循环 | `pytest.ini` 里把 fixture/test 的 loop scope 都设为 `session`，并在会话结束 dispose engine |
| 2026-10-19 | `refresh` 用例断言「令牌已轮换」失败 | JWT 的 `iat`/`exp` 精确到秒，同一秒内签发的令牌**完全相同** | 载荷加 `jti`（随机 hex），既保证唯一，也为将来做令牌吊销留了抓手 |
| 2026-10-19 | 前端 UI 自动化测试：`click` 报 `UnknownVizError`；`fill` 把文本**追加**到原值后面 | 折叠区域外的元素取不到可见性；`fill` 语义是「输入」不是「替换」 | 对折叠区外元素用 `evaluate` 触发 `click()`；改值用 React 原生 setter + 派发 `input` 事件；**按 label 文本定位字段**，不要用索引（禁用的用户名输入框也占一个位置） |
| 2026-10-19 | 上传中文名文件后，标题变成单个 `_` | multipart 的 `Content-Disposition` 文件名是原始 UTF-8 字节，被 HTTP 头按 latin-1 解码成乱码，再被「非字母数字替换成 `_`」的清洗规则抹平 | 新增 `fix_filename_encoding`（latin-1→utf-8 可逆还原）；清洗规则改为只去路径分隔符与控制字符，保留中文/空格/括号 |
| 2026-10-19 | 后端加了新路由，但运行中的服务一直 404 | `uvicorn --reload` 在 Windows 上只捕捉到一次变更，且父进程被杀后 reloader 的 multiprocessing 子进程成为孤儿继续占 8000 端口跑旧代码 | 用 `Get-CimInstance Win32_Process` 找到 CommandLine 含 uvicorn 的进程杀掉再重启；**本机开发不再用 `--reload`** |
| 2026-10-19 | antd 控制台又报两条废弃警告 | antd 6 继续改名：`Drawer.width`→`size`、`Space.direction`→`orientation` | 以控制台为准逐个修正；改完页面必须看控制台，不能只看「能渲染」 |
| 2026-10-19 | `fitz` 相关 DeprecationWarning | PyMuPDF 1.24+ 推荐 `import pymupdf`，`fitz` 是旧别名 | 改为 `import pymupdf as ...` 并更新调用 |
| 2026-10-19 | 改了 `router/index.tsx` 后前端没有新路由，访问 `/notes` 被兜底跳到 `/` | Vite 无法对导出常量（`router`）做 Fast Refresh，日志明确写 `Could not Fast Refresh ("router" export is incompatible)`；且旧 dev server 的转换缓存会继续返回旧模块 | 停掉**所有** vite 进程后重启（不是只 reload 页面）；已封装进 `scripts/dev.ps1` |
| 2026-10-19 | 端口 8000/5173 反复被上次残留的进程占用（含 uvicorn reloader 的孤儿 worker） | 每次会话结束/重启后进程不一定退出，且**父进程被杀后子进程仍持有 socket** | 新增 `scripts/dev.ps1`：先按端口 + 命令行双重清理，再原地启动前后端（后端固定 8000、前端固定 5173） |
| 2026-10-19 | `ZoneInfo('Asia/Shanghai')` 抛 `ZoneInfoNotFoundError` | Windows 与 alpine 镜像都没有系统 IANA 时区库；Python 的 zoneinfo 在这种情况下需要 PyPI 的 `tzdata` | 加依赖 `tzdata`（已进 requirements.txt）。凡是按业务时区切日/取「今天」都依赖它 |
| 2026-10-19 | `PATCH /plans` 带日期字段返回 200 但日期没改 | Pydantic 默认忽略未声明字段 | `PlanUpdate` 显式声明 `start_date`/`end_date`，service 检测到就抛 400。**要拒绝某字段必须先声明它** |
| 2026-10-19 | 工具包内 `from app.ai.tools import MAX_TOOL_CHARS` 报循环导入 | `tools/__init__.py` 既导出工具函数、又给子模块提供常量 | 常量单独放 `app/ai/tools/constants.py` |
| 2026-10-19 | 代码/测试里出现 `"B ??"` 这种被替换成 `?` 的中文 | 用 PowerShell here-string 往 Python 传中文时，管道按 ANSI 编码，多字节字符被替换为 `?` | 中文内容一律用编辑工具改，shell 只做 ASCII 替换；改完 grep `??` 复核 |
| 2026-10-19 | 探针第 3 项（流式）报 `ValueError: too many values to unpack` | 探针里用了裸 `model.stream()`（只产出 chunk），而 `(chunk, metadata)` 元组是 `graph.astream(stream_mode="messages")` 的形状 | 探针改为走**生产同款路径**（`create_agent` + `graph.astream(stream_mode="messages")`） |
| 2026-10-19 | OpenCode Zen 的 Key 能列模型但所有对话请求 402/403 | `/models` 只验证认证；对话要走结算层。付费模型 `Insufficient account funds`，免费模型 `FreeTierError` | 换回 DashScope（已 PASS）；换供应商只改 `.env` 三个变量 |
| 2026-10-19 | 总结接口偶发 `400 AI_005`（agent 步数超限），一次耗 16.7s | 总结/出题的服务层**已把正文放进 message**，但 agent 还挂了 `read_material_chunk`，模型会反复读同一段直到撞上 `ai_max_steps=12` | summary / quiz 场景**不挂工具**（正文已给），并同步改 prompt；重测：tokens 6651 → **870**，12.1s → **6.9s** |
| 2026-10-19 | 总结/出题在前端一直「请求超时」，但后端其实已经生成并落库 | axios 实例默认 `timeout: 15000`，而 AI 生成要走「模型调用 + 结构化重试」（后端 `ai_agent_timeout=90`） | 生成类接口单独传 `timeout: 180000`（`api/ai.ts` / `api/quizzes.ts`），列表/详情仍用默认 15s |
| 2026-10-19 | 后端测试 `test_generate_summary_persists_generation_and_usage` 突然断言失败（6215 ≠ 120） | 用例写的是 `select(AiUsage).where(scene=="summary")`，没排序也没按用户过滤；本地库里有真实模型跑出来的历史行 | 改为 `where(scene, user_id).order_by(created_at.desc()).limit(1)` —— 只断言本次请求写入的那行 |
| 2026-10-19 | 前端按 `/ai/quizzes` 取测试题列表 → 405 | 契约的方法表里「生成长在 `/api/v1/ai/quizzes`，其余在 `/api/v1/quizzes`」；想当然以为整个模块都在 `/ai` 下 | 以 `docs/api.md` 的**方法+路径表**为准；405 往往是「路径存在但方法不匹配」的信号 |
| 2026-10-19 | `GET /stats/daily` 报 `syntax error at or near ":"`，`:start` / `:end` 根本没被绑定 | `text()` 里写 `generate_series(:start::date, ...)`：绑定参数紧跟 `::` 类型转换时 SQLAlchemy 识别不出占位符，SQL 原样发给 PG。这段 SQL 是 M4 写的，**直到 M6 接上 HTTP 才第一次真正执行** | 改为 `CAST(:start AS date)`。教训：**「写完」不等于「能用」**——没有入口/用例覆盖的代码就是没验证过的代码，所以 M6 第一件事就是把契约里的补零用例补上 |
| 2026-10-19 | ECharts 6 提示 `grid.containLabel` 已废弃；antd 6 再报 `Button.iconPosition` 已废弃 | 两个库在 6.x 都改了名 | ECharts 用 `outerBoundsMode:'same' + outerBoundsContain:'axisLabel'`（官方给的等价写法）；antd 用 `iconPlacement` |
| 2026-10-19 | 改完 `StatsPage.tsx` 在页面上验证，控制台仍报旧警告 | Vite 的转换缓存又返回了旧模块（本项目第二次踩，第一次见上一条「router 常量」） | 验证前先 `fetch('/src/pages/StatsPage.tsx')` 看 dev server **实际服务的源码**是不是新版，必要时重启 vite；别对着旧模块下结论 |
| 2026-10-19 | echarts 全量导入把懒加载 chunk 撑到 1.13 MB | `import * as echarts from 'echarts'` 会把所有图表类型都打进来 | 改用 `echarts/core` + `use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])`，chunk 降到 568 KB（gzip 377 → 193 KB） |

---

## 4. M0 验收结果（2026-10-18 · 全部通过）

| M0 验收项 | 结果 | 证据 |
|---|---|---|
| FastAPI 可启动，`/health` 返回契约字段 | ✅ | 200/503 两条分支均有用例；OpenAPI 记录 `HealthOut` 与 503 |
| 前端 Vite + React 19 + antd 6 可构建可运行 | ✅ | `tsc --noEmit` 通过；产物 844 kB / gzip 276 kB；浏览器控制台零警告 |
| 前端经代理调通后端 `/health` | ✅ | 浏览器网络面板：`GET http://127.0.0.1:5173/health -> 200` |
| Alembic 异步迁移可生成并**在线执行**首个版本（含 pg_trgm） | ✅ | `alembic_version = 161c601b0154`；`pg_extension` 含 `pg_trgm 1.6` |
| PostgreSQL 可用，`/health` 返回 `db=ok` | ✅ | `curl /health` → `{"status":"ok","db":"ok","version":"0.1.0"}`；页面显示「数据库: ok」 |
| pytest 冒烟用例通过（含真实数据库集成用例） | ✅ | `4 passed`（集成用例不再 skip）；`-m integration` → 1 passed |
| ruff 静态检查通过 | ✅ | `All checks passed!` |
| 数据库环境 | ✅ | PostgreSQL **18.6** on x86_64-pc-linux-musl，库 `smart_learning`，用户 `app` |

**M0 实际投入（校准基准，用于修正后续估算）**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 环境探测 + 依赖安装 | ~10 min | pip 走清华镜像约 3 min；npm 2 min |
| 后端骨架（配置/引擎/健康检查/测试） | ~40 min | 含 6 处环境与编码问题排查 |
| Alembic 异步配置 + 首个迁移 | ~25 min | 其中约 15 min 耗在 `alembic.ini` 编码与 ruff 误判上 |
| 前端骨架 + 构建验证 | ~25 min | 一次通过，无返工 |
| antd 6 废弃 API 排查与修复 | ~10 min | 靠浏览器控制台发现，源码层面看不出来 |
| **Docker / 数据库环境打通** | **~40 min** | 凭据助手 PATH、镜像加速、PG18 挂载点变更（三处都不是代码问题） |
| 端到端联调验证 | ~15 min | 代理、路由校验、浏览器验证 |
| **合计** | **约 2.5–3 小时** | 原估 8–12 h（人工手写基准） |

> **两条结论**：
> 1. AI 辅助下，代码部分约为人工基准的 **1/4~1/5**；
> 2. 但**环境类问题不因 AI 而减少** —— 本次约 **45%** 的时间花在 Docker/编码/组件 API 变更上，这类时间要按原值预留，甚至要额外加。

---

## 5. M1 验收结果（2026-10-19 · 全部通过）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 注册 / 登录 / 刷新 / 登出 | ✅ | 后端 41 个用例；浏览器端到端全流程走通 |
| 令牌失效机制 | ✅ | 改密码后旧 access 令牌 → 401 `AUTH_003`（用例覆盖）；`token_version` 机制生效 |
| 个人信息读写 | ✅ | 浏览器改昵称/每日目标 → 库中持久化为 `UI改名成功` / `90` |
| 前端路由守卫 | ✅ | 未登录访问 `/` → 跳 `/login`；登出后刷新 `POST /auth/refresh -> 401`，不恢复会话 |
| 刷新页面保持登录 | ✅ | `POST /auth/refresh -> 200`（httpOnly Cookie），URL 停在 `/`，控制台零错误 |
| 统一错误体 | ✅ | 实测 `SYS_422` / `AUTH_001` / `AUTH_003` / `USER_003` 均带 `code`+`message`+`detail` |
| 契约先行 | ✅ | 新增 `AUTH_005`、`USER_004` 与邮箱校验口径已回写 `docs/api.md` |
| 测试不污染数据 | ✅ | 全套用例跑完 `app_user` 仍只有 1 行 e2e 数据（外层事务回滚生效） |
| 头像上传 | ⏳ 推迟 | 按计划放 M2，与资料上传共用文件存储与 MIME 校验 |

**M1 安全行为实测（2026-10-19）**

| 验证项 | 结果 |
|---|---|
| 密码只存 Argon2id 哈希 | ✅ `$argon2id$v=19$m=65536,t=3,p=4$...`；全库 `pg_dump` 中搜不到明文密码 |
| 登录响应不含密码字段 | ✅ 只有 `{access_token, token_type, expires_in, role}` |
| JWT 载荷不含敏感信息 | ✅ 仅 `{sub, pv, typ, jti, iat, exp}`；`access` 有效期 1800s、`refresh` 604800s |
| refresh Cookie 属性 | ✅ `HttpOnly; Max-Age=604800; Path=/api/v1/auth; SameSite=lax` |
| 密码错误 / 用户不存在 | ✅ 两者都返回 401 `AUTH_003` + 完全相同的文案（不泄露账号是否存在） |
| 账号被禁用 | ✅ 正确密码后才返回 403 `USER_003`（先验密码再报禁用，避免账号枚举） |
| 数据隔离 | ✅ 两个用户的令牌各自只能读到自己的 `/users/me` |
| 数据库层认证 | ⚠️ 本机为 `trust`（官方镜像默认），**不是**缺陷但需知晓，见 `docs/db.md` §1.1 |

**M1 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 契约补充（2 个错误码 + 邮箱口径） | ~10 min | 契约先行，先改文档再写代码 |
| 后端（模型/迁移/安全/异常/依赖/service/路由） | ~50 min | 迁移踩了 SQLModel `AutoString` 的坑 |
| 后端测试（41 例 + 事务隔离 fixture） | ~35 min | 其中一半时间在排查事件循环作用域问题 |
| 前端（网络层/登录态/5 个页面/守卫） | ~50 min | 一次构建通过，无类型返工 |
| 联调与排障（5 个坑） | ~40 min | 事件循环、jti、AutoString、浏览器工具定位 |
| **合计** | **约 3 小时** | 原估 12–16 h（人工基准），约 1/4 |

> 新增依赖：`email-validator`（Pydantic `EmailStr` 需要）—— 已登记进 `requirements.txt` 与本节 §1。

---

## 6. M2 验收结果（2026-10-19 · 全部通过）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 上传 PDF/DOCX → 202 + 后台解析 | ✅ | 真实 DOCX：78 字；真实 PDF：2 页 / 216 字 |
| 扫描版 PDF | ✅ | `parse_status=unsupported`，不抛错（前端提示暂不支持 OCR） |
| 类型 / 魔数 / 大小校验 | ✅ | 400 `MAT_003`（.txt、伪装 .pdf）；413 `MAT_002`（超限） |
| **中文文件名** | ✅ | `高数第一章.docx` → 库中 `title=高数第一章`（修复前是 `_`） |
| 正文分片 | ✅ | `offset/limit` + `has_more`；与 M5 的 agent 工具共用同一 service |
| 鉴权下载 | ✅ | `Content-Disposition: attachment; filename*=UTF-8''...`，返回原始字节 |
| 越权隔离 | ✅ | 另一账号 GET/下载/正文/删除 → 全部 404 `SYS_404` |
| 软删除 + 删文件 | ✅ | 204 后详情 404，磁盘文件确实不存在 |
| 重解析 | ✅ | `success` → 400；`failed` → 202 |
| 前端页面 | ✅ | 表格 3 行、状态标签、正文抽屉、上传组件均正常；**控制台零警告** |
| 测试隔离 | ✅ | 用例把 `upload_dir` 指向 tmp_path，不污染 `backend/storage/` |

**M2 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 后端（模型/迁移/存储/解析/service/路由） | ~70 min | 迁移一次生成即正确（ARRAY、GIN、trgm、部分索引都对） |
| 后端测试（81 例，新增 34 例） | ~40 min | 含真实生成的 DOCX/PDF 样本 |
| 前端（资料页/懒加载/头像组件） | ~50 min | 顺带做了路由级代码分割 |
| 联调排障 | ~45 min | 中文文件名、reload 孤儿进程、两条 antd 警告 |
| **合计** | **约 3.5 小时** | 原估 12–16 h |

---

## 7. M3 验收结果（2026-10-19 · 全部通过）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 笔记 CRUD | ✅ | 后端 14 个用例 + 浏览器「新建→保存→出现在列表」闭环 |
| 列表不返回正文 | ✅ | 列表项字段恰为 `{excerpt,id,material_id,tags,title,updated_at}`；300 字正文的摘要为 121 字 |
| 搜索（标题 + 正文） | ✅ | `keyword=ε-δ` 命中正文中的笔记 |
| 标签 / 关联资料过滤 | ✅ | `tag=重点`、`material_id=...` 各命中 1 条 |
| 关联资料归属校验 | ✅ | 引用别人的资料 → 404（不暴露存在性） |
| 正文上限 | ✅ | 100001 字 → 422 `SYS_422` |
| 越权隔离 | ✅ | 他人笔记的读/改/删全部 404，列表也看不到 |
| 前端 | ✅ | 表格 + 摘要 + 抽屉编辑器；控制台零警告 |
| 表结构 | ✅ | `04b1a5253a70`；`note` 表 9 列 / 6 索引（含 2 个 trgm GIN）/ FK `ON DELETE SET NULL` |
| Swagger 错误码 | ✅ | 每个接口都标注了 401/403/404/409/400/413 等真实取值 |

**M3 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 后端（模型/迁移/schema/service/路由） | ~40 min | 迁移一次生成即正确 |
| 后端测试（14 例） | ~25 min | 含隔离与上限用例 |
| 前端（笔记页 + 抽屉编辑器） | ~35 min | 顺带抽了 `utils/text.py` 复用标签逻辑 |
| Swagger 错误码标注 | ~20 min | 逐个接口按实际可能的状态码声明 |
| 联调排障（Vite HMR / 端口） | ~45 min | 见 §3 的 Vite 条目与 `scripts/dev.ps1` |
| **合计** | **约 2.5–3 小时** | 原估 6–8 h |

---

## 8. M4 验收结果（2026-10-19 · 全部通过）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 计划 CRUD | ✅ | 32 个新用例；浏览器三个 Tab 均正常，控制台零警告 |
| 计划区间校验 | ✅ | 结束早于开始 → 422；区间 >180 天 → 422 |
| 日期不可改 | ✅ | `PATCH /plans` 带 `start_date` → 400 `SYS_400`（而不是静默忽略） |
| **生成任务幂等** | ✅ | 首次 created=5；再次 → 409 `PLAN_001` |
| **删任务后可补生成** | ✅ | 删掉 1 条再生成 → `created=1, skipped=4`（部分唯一索引的价值） |
| 重建（overwrite） | ✅ | 已完成的任务保留，其余 4 天重建 |
| **完成任务的原子性** | ✅ | 一次调用同时置 done 并写入 study_record（时长 50 分钟已核验） |
| 重复完成 | ✅ | 第二次 → 400 `SYS_400` |
| 计划进度口径 | ✅ | 5 个任务完成 1 个 → `1/5 = 0.2`；`skipped` 不计入总数 |
| 级联软删 | ✅ | 删计划后未完成任务消失，已完成任务保留（用于统计） |
| 学习记录 | ✅ | 按业务时区的「今天」过滤、按类型、按计划（经任务关联）过滤均正确 |
| 未来时间校验 | ✅ | 开始时间超当前 +5 分钟 → 422；+2 分钟容忍通过 |
| 越权隔离 | ✅ | 计划/任务/记录三处读改写全部 404，列表为空 |
| 新增依赖 | ✅ | `tzdata`（Windows/alpine 缺系统时区库必需） |

**M4 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 后端（3 张表 + 3 个 service + 3 个路由） | ~75 min | 逻辑量最大的一轮 |
| 后端测试（32 例） | ~40 min | 幂等、原子性、时区、隔离是重点 |
| 前端（计划页三 Tab） | ~50 min | 复用表格/弹窗模式，速度明显加快 |
| 联调排障（tzdata / 端口 / lint） | ~30 min | 见 §3 |
| **合计** | **约 3–3.5 小时** | 原估 12–16 h |

---

## 9. M5 验收结果（后端 + 前端，2026-10-19）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 6 张新表 | ✅ | `26484908c0ac`：quiz / quiz_attempt / chat_session / chat_message / ai_generation / ai_usage |
| 结构化输出校验 | ✅ | 18 条用例：数量/题型/选项重复/答案越界/题干重复 → 硬伤；编号、判断题选项、填空题选项、难度 → 自动修正 |
| 判分规则 | ✅ | 单选忽略大小写、多选**完全一致**才算对、填空忽略大小写与空白 |
| 只读工具 | ✅ | 6 个工具：信封结构、`user_id` 闭包隔离、`%` 转义、截断标志、`BAD_DATE`/`BAD_STATUS` 等错误对象 |
| 统计聚合 | ✅ | 完成率不算 skipped；「今天」按业务时区；趋势补零 |
| 用量与配额 | ✅ | 一次请求一行；token 为 agent 多轮累加；配额超限 → 429 `AI_004` |
| 未配置 Key | ✅ | 503 `SYS_503`（不是 500） |
| 建议的后端覆盖 | ✅ | 模型编造的 `weak_points`/`next_7_days` 被后端计算结果覆盖，且每日时长不超过目标的 1.5 倍 |
| SSE 流式 | ✅ | 事件序列 meta → delta* → done；`text/event-stream` 头正确 |
| 问答会话 | ✅ | 消息落库（user/assistant）、首问更新标题、跨用户 404 |
| **前端 AI 页面** | ✅ | `/ai` 一页 4 个 Tab：智能问答（SSE 打字机 + 工具标签 + 停止）、资料总结、测试题（生成 → 答题 → 交卷判分 → 成绩历史）、学习建议；顶栏实时显示今日调用/配额/token/成功率 |
| **能力探针** | ✅ | DashScope `qwen-plus` 三项全 PASS：工具调用 1.7–2.1s、结构化 5.3s、流式 0.5s（§2） |
| **真实模型端到端** | ✅ | 总结 201（9 条要点 / 870 tokens / 6.9s）；出题 201（5 题）；判分 60 分（未答 2 题按错，逐题明细与解析正确）；建议 201（`next_7_days` 每日被压到 90 分钟 = 60×1.5）；问答 200（`read_material_chunk` 命中，`done` 后消息落库） |
| **浏览器实测** | ✅ | 登录 → `/ai` → 4 个 Tab 全部可操作；控制台 0 报错（antd 废弃警告已清零）；SSE 流式回答完整呈现 |

**M5 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 6 张表 + 迁移 | ~30 min | 一次生成即正确（JSONB / ARRAY / CHECK / 部分索引） |
| AI 层（llm / schemas / validators / prompts / tools / agents / runtime / usage） | ~90 min | 最费脑的一层：超时、步数、用量累加、异常映射 |
| 4 个功能 service + API | ~60 min | 总结含 map-reduce；建议含后端覆盖 |
| 测试（39 条新增） | ~50 min | 打桩点选在 `invoke_structured`，真实链路其余部分都被测到 |
| 前端 4 个 Tab | ~80 min | 手写 SSE 解析（EventSource 不支持 POST）、生成→答题→判分三个弹窗 |
| 联调排障 | ~40 min | 三个真实缺陷：超时 15s、工具回环、契约路径（见 §3） |
| 排障（循环导入 / 中文写成 `?` / lint） | ~35 min | 见 §3 |
| **合计** | **约 6.5 小时** | 原估 30–45 h（人工基准） |

---

## 10. M6 验收结果（统计图表 + 个性化推荐 + 全局异常，2026-10-19 · 全部通过）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 统计接口 | ✅ | `GET /stats/overview`、`/stats/daily`、`/stats/subjects`、`/stats/weak-points`（契约 §12.1） |
| 趋势补零 | ✅ | `daily` 用 `generate_series` 补日：5 天区间**必返 5 条**，没数据的日期是 0 而不是缺行 |
| 统计口径 | ✅ | skipped 不进完成率分母；日期按 `APP_TIMEZONE` 切分；空账号各项为 0 且 `task_completion_rate=0.0`（不除零、不为 null） |
| 科目分布 | ✅ | 归到计划科目，无计划归属的记录进「未分类」；`task_done` 去重计数 |
| 薄弱知识点 | ✅ | 从 `quiz.question_data.knowledge` 展开，样本 < 3 次被过滤（避免「错 1 次就算薄弱」） |
| 个性化推荐（功能 10） | ✅ | 规则层 5 类：`task` / `review` / `plan` / `material` / `habit`，按优先级返回并支持 `limit`；**不调模型、不耗配额、秒回** |
| 推荐与 AI 建议的分工 | ✅ | 规则层 `/recommendations`（可解释）+ AI 层 `/ai/advice/generate`（叙述性），两条线互不替代 |
| 全局异常 | ✅ | 未预期异常 → 500 `SYS_500`，响应体**不含堆栈与异常文本**（新增用例断言）；`AppError` / 422 / HTTPException 早已统一 |
| 前端统计页 | ✅ | `/stats`：6 张指标卡 + 时长/任务双轴图 + 科目饼图 + 正确率趋势 + 薄弱知识点表；7/30/90 天切换 |
| 前端工作台 | ✅ | 「今天做什么」推荐卡（每条可跳转到对应页面）+ 今日任务 + 近 7 天概览；删掉了 M1 时代的「当前进度」占位块 |
| 跳转可用性 | ✅ | 推荐里的 `/plans?tab=tasks`、`/plans?tab=records` 真的会切到对应 Tab（PlansPage 已与地址栏同步） |
| 浏览器实测 | ✅ | 真实数据渲染（50 分钟 / 活跃 1 天 / 正确率 57% / 2 次答题）；3 个图表 canvas 均绘制成功；控制台 0 报错 |
| 打包体积 | ✅ | ECharts 按需注册后，`StatsPage` 懒加载 chunk 1.13 MB → 568 KB（gzip 377 → 193 KB） |

**M6 实际投入**

| 环节 | 实际耗时 | 说明 |
|---|---|---|
| 契约补齐（§12 拆分 + 功能 10 推荐） | ~20 min | 先写清「规则层 vs AI 层」的分工与 5 类触发条件 |
| 统计接口 + 推荐 service | ~50 min | 复用 `stats_service` 口径；推荐是纯规则、只读 |
| 测试（16 条新增） | ~45 min | 含把 M4 潜伏的 `daily` SQL bug 逼出来的补零用例 |
| 前端统计页 + 工作台改造 | ~70 min | EChart 轻封装（按需注册）、双轴图、饼图、趋势图、推荐卡 |
| 排障（SQL 绑定 / 两个 6.x 改名 / Vite 缓存） | ~35 min | 见 §3 |
| **合计** | **约 3.5 小时** | |

---

## 11. 待确认事项

| 项 | 状态 | 结论 |
|---|---|---|
| 管理员端是否需要 | **已确认为功能 13（独立编号）** | 子模块 13.1–13.5；新增 2 张表；工作量 +18~26h；论文需求分析中独立成节 |
| 异步 Alembic 配置是否一次跑通（M0 卡壳则整体降级同步 Session） | ✅ 已跑通 | 异步模板 + `compare_type` 可用，无需降级为同步 Session |
| PostgreSQL 环境来源 | ✅ 已完成 | Docker Desktop 4.95 + `postgres:18-alpine`（PG 18.6）；一键脚本 `deploy/setup-db.ps1`；国内网络需配 registry-mirrors，且 PG18 挂载点为 `/var/lib/postgresql`（见 §3） |
| `deepagents` 是否对 `advice` 场景有实际收益（M7 后评估） | 待评估 | |
| 是否升级 `study_plan.material_ids` 数组 → 关联表（若要求严格 3NF） | 待定 | |
