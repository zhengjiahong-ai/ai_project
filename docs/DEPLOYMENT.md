# Pixiu 生产部署指南

## 环境变量清单

### 必填

| 变量 | 说明 | 示例 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | `sk-...` |

### LLM 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 主模型 |
| `DEEPSEEK_TRANSLATION_MODEL` | `deepseek-v4-flash` | 翻译/轻量模型 |
| `DEEPSEEK_TEMPERATURE` | `0.3` | 主模型温度 |
| `DEEPSEEK_TRANSLATION_TEMPERATURE` | `0.1` | 翻译模型温度 |
| `DEEPSEEK_THINKING_TYPE` | `enabled` | thinking 模式 |
| `DEEPSEEK_REASONING_EFFORT` | `high` | 推理深度 |
| `DEEPSEEK_TIMEOUT_SECONDS` | `120` | API 超时（秒） |

### Pixiu 功能开关

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_LLM_MODE` | `deepseek` | LLM 模式（`deepseek` / `fixture`） |
| `PIXIU_MCP_ENABLED` | `false` | 启用 MCP adapter |
| `PIXIU_MCP_TRANSPORT` | `stdio` | MCP 传输（`stdio` / `sse`） |
| `PIXIU_MCP_SSE_HOST` | `127.0.0.1` | SSE 监听地址 |
| `PIXIU_MCP_SSE_PORT` | `8001` | SSE 端口 |
| `PIXIU_MCP_AUTH_TOKEN` | (空) | MCP 认证 token |
| `PIXIU_ALLOW_BROWSER` | `false` | 启用 headless 浏览器 |
| `PIXIU_ALLOW_REPRODUCIBILITY` | `false` | 启用实验复现 |

### 运行时参数

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_LOG_LEVEL` | `INFO` | 日志级别 |
| `PIXIU_LOG_JSON` | `false` | JSON 格式日志 |
| `PIXIU_AGENTIC_MAX_ITERATIONS` | `3` | 迭代搜索最大轮数 |
| `PIXIU_MAX_TOKENS_PER_TASK` | `500000` | 任务 token 预算 |
| `PIXIU_SESSION_TOKEN_BUDGET` | `2000000` | 会话 token 预算 |
| `PIXIU_TASK_POOL_SIZE` | `2` | 任务池大小 |

### 可信度权重（14-2）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_CREDIBILITY_CURRENT_PAPER_WEIGHT` | `1.0` | 当前论文权重 |
| `PIXIU_CREDIBILITY_LIBRARY_WEIGHT` | `0.85` | 文献库权重 |
| `PIXIU_CREDIBILITY_EXTERNAL_ACADEMIC_WEIGHT` | `0.65` | 外部学术权重 |
| `PIXIU_CREDIBILITY_WEB_SEARCH_WEIGHT` | `0.45` | Web 搜索权重 |
| `PIXIU_CREDIBILITY_WEB_PAGE_WEIGHT` | `0.40` | 网页权重 |
| `PIXIU_CREDIBILITY_DEFAULT_WEIGHT` | `0.30` | 未知来源默认权重 |

### LLM 缓存（15-2）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_LLM_CACHE_MODE` | `exact` | 缓存模式（`exact` / `semantic`） |
| `PIXIU_LLM_CACHE_TTL_MINUTES` | `60` | 缓存 TTL（分钟） |
| `PIXIU_LLM_CACHE_PATH` | `data/llm_cache.sqlite3` | 缓存路径 |

### 限流（15-3）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_RATE_LIMIT_ENABLED` | `true` | 启用限流 |
| `PIXIU_RATE_LIMIT_GLOBAL_RPM` | `60` | 全局速率（req/min） |
| `PIXIU_RATE_LIMIT_AGENT_RPM` | `10` | Agent 任务速率 |
| `PIXIU_RATE_LIMIT_CHAT_RPM` | `30` | 聊天速率 |
| `PIXIU_RATE_LIMIT_TRANSLATE_RPM` | `10` | 翻译速率 |

### 认证（19-1）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PIXIU_API_AUTH_TOKEN` | (空) | 设置后启用 Bearer token 认证 |

### 外部服务

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GROBID_SERVER_URL` | `http://grobid:8070` | GROBID 地址 |
| `SEMANTIC_SCHOLAR_API_KEY` | (空) | Semantic Scholar API Key |
| `NEO4J_URI` | (空) | Neo4j 连接 URI |

### 前端环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8081/api` | 阅读 IDE API |
| `VITE_AGENT_API_BASE_URL` | `http://localhost:8081/api` | Agent API |

---

## Docker 单机部署

```bash
git clone <repo-url> && cd ai_project
cp .env.example .env
# 编辑 .env，填写 DEEPSEEK_API_KEY

docker compose up -d --build
```

服务端口：
- 前端：`http://localhost:5173`
- Java 网关：`http://localhost:8081`
- Python AI：`http://localhost:8000`
- GROBID：`http://localhost:8070`

健康检查：
```bash
curl http://localhost:8000/api/health
```

日志：
```bash
docker compose logs -f ai-service
docker compose logs -f backend
```

---

## 裸机部署

### Python AI 服务

```bash
cd ai-service-python
pip install -r requirements.txt
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

生产环境建议使用 `gunicorn` + `uvicorn` worker，CPU 核心数 + 1 个 worker。

### Java 网关

```bash
cd backend-java
./mvnw package -DskipTests
java -jar target/backend-java-*.jar --server.port=8081
```

建议通过 systemd 管理：
```ini
[Unit]
Description=Pixiu Java Gateway
After=network.target

[Service]
User=pixiu
WorkingDirectory=/opt/pixiu/backend-java
ExecStart=/usr/bin/java -jar target/backend-java-*.jar --server.port=8081
Restart=always

[Install]
WantedBy=multi-user.target
```

### 前端

```bash
cd frontend
npm install
npm run build
# 将 dist/ 部署到 nginx
```

nginx 配置示例：
```nginx
server {
    listen 80;
    server_name pixiu.example.com;

    root /opt/pixiu/frontend/dist;
    index index.html;

    location / {
        try_files $uri /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /share/ {
        try_files $uri /index.html;
    }
}
```

---

## 数据持久化

### SQLite 数据库

| 路径 | 用途 | 环境变量 |
|---|---|---|
| `data/research_tasks.sqlite3` | Deep Research 快照 | `RESEARCH_TASK_DB_PATH` |
| `data/agent_state.sqlite3` | Agent 项目/任务 | `AGENT_STATE_DB_PATH` |
| `data/knowledge_graph.sqlite3` | 知识图谱 | `KNOWLEDGE_GRAPH_DB_PATH` |
| `data/code_execution.sqlite3` | 代码执行审计 | `CODE_EXECUTION_DB_PATH` |
| `data/llm_cache.sqlite3` | LLM 缓存 | `PIXIU_LLM_CACHE_PATH` |
| `data/shares.sqlite3` | 分享 token | `PIXIU_SHARE_DB_PATH` |

备份策略：SQLite 文件可直接复制（`.backup` 命令或 `cp`），建议每日 cron 备份到外部存储。

### ChromaDB

数据目录：`chroma_data/`（通过 `CHROMA_DB_PATH` 配置）
Docker volume：`chroma_data`

### Java H2

数据目录：`java_data/`（Docker volume `java_data`）
备份：复制 `*.mv.db` 文件。

---

## 安全建议

1. **启用 API 认证**：设置 `PIXIU_API_AUTH_TOKEN` 保护写操作端点。
2. **启用限流**：保持 `PIXIU_RATE_LIMIT_ENABLED=true`（默认）。
3. **HTTPS 反代**：生产环境始终在 nginx/Caddy 层启用 HTTPS。
4. **不暴露内部端口**：GROBID（8070）、ChromaDB、Neo4j 不应绑定到公网 IP。
5. **环境变量隔离**：`.env` 文件权限设为 `600`，不提交到 Git。
6. **定期清理**：LLM 缓存（TTL 自动过期）、分享 token（7 天自动过期）。
7. **日志脱敏**：生产环境设置 `PIXIU_LOG_JSON=true` 便于日志聚合，注意 `SanitizingFormatter` 已自动过滤 API key、论文全文和用户消息。
