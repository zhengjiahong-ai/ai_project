# 使用轻量级 Python 镜像
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 拷贝代码
COPY . .

EXPOSE 8000

# 启动 FastAPI。容器内禁用 --reload，避免 watchfiles 扫描 bind mount 中的残留临时目录后崩溃。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

ENV CHROMA_DB_DIR=/app/chroma_data
RUN mkdir -p /app/chroma_data
