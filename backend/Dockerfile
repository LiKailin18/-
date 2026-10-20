# 后端生产镜像（M7）。
# 单命令启动：先跑 Alembic 迁移，再起 uvicorn。
# 依赖 compose 的 depends_on: postgres(healthy) 保证库先就绪；
# 若迁移瞬间库还没完全接受连接，restart: unless-stopped 会重试。

FROM python:3.12-slim

WORKDIR /app

# 只装生产依赖，利用层缓存。
# 先升级 pip：镜像自带的 25.0.1 有哈希校验误报（干净的无 hash requirements 也会报
# "THESE PACKAGES DO NOT MATCH THE HASHES"），本机 venv 用的 26.2.1 无此问题。
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# 上传文件落盘目录（compose 用 volume 持久化）
RUN mkdir -p /app/storage

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
