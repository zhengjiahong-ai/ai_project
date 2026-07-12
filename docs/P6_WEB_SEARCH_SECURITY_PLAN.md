# P6-05 Web 搜索安全模型

## 概述

本文档定义 Pixiu Web 搜索与页面抓取的完整威胁模型、安全边界和前置安全措施。所有后续 Web 搜索 Provider（Brave P6-06、Tavily P6-07）、`search_web` 工具（P6-08）和页面抓取功能（P6-09–P6-12）均以此文档为安全基线。

## 威胁模型

### 攻击面

| 攻击向量 | 风险等级 | 描述 |
|----------|----------|------|
| SSRF（服务端请求伪造） | 高 | 通过构造恶意 URL 访问内网服务或云元数据端点 |
| DNS 重绑定 | 高 | 攻击者控制的域名先解析为白名单 IP，后改为内网 IP |
| 提示注入 via 抓取内容 | 高 | 抓取的 Web 页面包含越权指令 |
| 恶意重定向 | 中 | HTTP 3xx 重定向到非白名单 host |
| 数据泄露 | 中 | URL 参数包含敏感信息或 API Key |
| 内容投毒 | 中 | 恶意页面返回虚假学术内容 |
| 资源耗尽 | 中 | 超大响应体导致内存/磁盘耗尽 |
| 不适宜内容 | 低 | 抓取到色情、暴力、恶意软件相关内容 |
| 版权违规 | 低 | 抓取付费墙内容或大量全文 |

### 不在范围内的威胁

- 搜索引擎 API 提供商（Brave、Tavily）的认证安全 — 由各 Provider 实现负责
- 通用 Web 爬虫 — 只抓取用户已授权的特定 URL
- 浏览器端安全 — 前端不直接发起 Web 搜索或页面抓取

## 安全边界

### 信任层级

```
┌────────────────────────────────────────────────┐
│                  用户授权                        │
│  allowWebSearch=true                           │
│  allowPageFetch=true                           │
├────────────────────────────────────────────────┤
│               URL 白名单校验                     │
│  validate_fetch_url(url)                       │
│  - HTTPS only                                  │
│  - host 在白名单内                              │
│  - 非 IP 地址                                  │
│  - 非 localhost                                │
├────────────────────────────────────────────────┤
│              DNS 解析与 IP 检查                  │
│  - 解析域名 → IP 列表                           │
│  - 拒绝私有/回环/链路本地/组播地址              │
├────────────────────────────────────────────────┤
│             HTTPS 强制                          │
│  - allow_redirects=False                       │
│  - Content-Type 预检查                          │
│  - 2 MiB 上限                                   │
├────────────────────────────────────────────────┤
│             内容安全处理                         │
│  - 提示注入检测                                │
│  - 代码标记/安全分级                            │
│  - Token 截断                                   │
├────────────────────────────────────────────────┤
│             证据模型                            │
│  - 来源可信度标记                               │
│  - 不覆盖内部证据                               │
│  - 不自动裁决冲突                               │
└────────────────────────────────────────────────┘
```

## URL 白名单

### 设计原则

1. **代码内硬编码** — 白名单定义在 `services/url_whitelist.py`，不可由模型、外部响应或用户输入修改
2. **按类别组织** — 六个类别：学术出版商、政府、组织、新闻、百科、代码仓库
3. **仅 HTTPS** — 所有 fetch 必须通过 HTTPS，拒绝 HTTP 和其他协议
4. **无名 DNS 重绑定防护** — 每次抓取前解析 DNS 并检查返回 IP

### 类别与覆盖范围

| 类别 | 键名 | 覆盖范围 | 示例 |
|------|------|----------|------|
| 学术出版商 | `academic_publishers` | Nature, Science, IEEE, ACM, Springer, Elsevier, Cell, NEJM, Lancet, JAMA, APA, Taylor &amp; Francis, Wiley, Sage, Oxford, Cambridge, MIT Press, PNAS, BMJ, PLOS, Frontiers, MDPI, eLife, Royal Society, AIP, APS, bioRxiv 等 | `*.nature.com`, `*.ieee.org`, `*.springer.com` |
| 政府 | `government` | .gov, .nih.gov, .nsf.gov, .nasa.gov, .europa.eu, .who.int, .un.org, CDC, FDA, EPA, DOE, USPTO 等 | `*.gov`, `*.nih.gov`, `*.who.int` |
| 组织 | `organizations` | arXiv, Semantic Scholar, Crossref, DOI, ORCID, DataCite, Zenodo, Figshare, OSF | `*.arxiv.org`, `*.semanticscholar.org`, `*.doi.org` |
| 新闻 | `news` | Reuters, AP News, BBC, NPR, The Economist, Nature News, Scientific American, New Scientist | `*.reuters.com`, `*.bbc.com`, `*.bbc.co.uk` |
| 百科 | `encyclopedia` | Wikipedia, Britannica | `*.wikipedia.org`, `*.britannica.com` |
| 代码仓库 | `code_repos` | GitHub, GitLab, Bitbucket, SourceForge, PyPI, CRAN, Bioconductor | `*.github.com`, `*.gitlab.com` |

## `validate_fetch_url(url)` 验证链

```
输入: url (str)

1. 类型检查        → 拒绝 None、非字符串、空字符串
2. URL 解析        → urlparse(url)，解析失败则拒绝
3. 协议检查        → 仅允许 "https" scheme
4. 凭证检查        → 拒绝包含 username/password 的 URL
5. Hostname 提取   → 提取并小写化 hostname，去掉尾部点
6. IP 地址拒绝     → 若 hostname 是原始 IP 地址（IPv4/IPv6），直接拒绝
7. localhost 拒绝  → 拒绝 "localhost" 和 "localhost.localdomain"
8. 白名单匹配      → hostname 必须匹配至少一个白名单模式（fnmatch 通配符）
9. DNS 解析        → 解析 hostname 到 IP 地址列表
10. IP 范围检查    → 逐 IP 检查是否为内部/私有/保留地址
11. 返回 hostname  → 成功时返回规范化的 hostname 字符串

任何一步失败 → 抛出 ValueError（错误信息不含原始 URL）
```

### 内部 IP 范围

以下 IP 范围在任何情况下均不可访问：

**IPv4:**
- `0.0.0.0/8` — 当前网络
- `10.0.0.0/8` — 私有 A 类
- `127.0.0.0/8` — 回环
- `169.254.0.0/16` — 链路本地
- `172.16.0.0/12` — 私有 B 类
- `192.168.0.0/16` — 私有 C 类
- `224.0.0.0/4` — 组播
- `240.0.0.0/4` — 保留

**IPv6:**
- `fc00::/7` — 唯一本地地址
- `fe80::/10` — 链路本地
- `::1/128` — 回环

## Blocklist 放松

### `_RESEARCH_SUBQUESTION_BLOCKLIST` 修改

**修改前:**
```
web\s*search|browse|internet|online|tool|plugin|mcp|agent|execute\s+command|
联网|上网|浏览网页|访问互联网|调用工具|调用插件|调用MCP|执行命令
```

**修改后:**
```
tool|plugin|mcp|agent|execute\s+command|
调用工具|调用插件|调用MCP|执行命令
```

### 移除项

| 移除的英文模式 | 移除的中文模式 | 原因 |
|---------------|---------------|------|
| `web\s*search` | `联网` | Web 搜索现在是授权的用户操作 |
| `browse` | `上网` | 浏览现在是授权的用户操作 |
| `internet` | `浏览网页` | 互联网访问现在是授权的 |
| `online` | `访问互联网` | 在线资源访问现在是授权的 |

### 保留项

| 保留的模式 | 原因 |
|-----------|------|
| `tool`, `plugin`, `mcp`, `agent` | 仍然是危险的权限提升攻击 |
| `execute\s+command` | 命令执行攻击 |
| `调用工具`, `调用插件`, `调用MCP`, `执行命令` | 中文等效危险指令 |

### 注意: `_INJECTION_PATTERNS` 不变

`_INJECTION_PATTERNS` 中的 `external_browsing` 检测保持不变 — 它检测的是不可信论文内容中的注入指令，而非用户授权的 Web 搜索请求。这两条路径是独立的。

## 安全不变量

所有后续 Web 搜索和页面抓取实现必须满足以下不变式：

1. **白名单不可绕过** — 任何 fetch 操作必经 `validate_fetch_url()`
2. **白名单不可修改** — 运行时不可增删白名单条目
3. **HTTPS 不可降级** — 不允许 HTTP、FTP、file 等协议
4. **重定向不可跟随** — `allow_redirects=False` 在所有 HTTP 请求中
5. **内网不可访问** — DNS 解析后 IP 必须全部是公网地址
6. **API Key 不泄露** — 认证 header 不入 trace/log/cache/模型上下文
7. **原始 URL 不入错误消息** — 所有错误消息经过脱敏
8. **外部内容不覆盖内部证据** — 证据优先级固定
9. **默认关闭** — Web 搜索和页面抓取仅当任务显式授权且 Provider 配置完整时启用
10. **预算硬上限** — 次数、字符数和延迟均有硬上限，耗尽后降级

## 审计要求

- 每次 `validate_fetch_url()` 调用应记录脱敏摘要（不包含完整 URL）
- DNS 解析失败应记录为安全事件（可能的重绑定尝试）
- 白名单外 URL 请求应记录并告警
- 内部 IP 解析应记录为严重安全事件

## 相关文件

| 文件 | 说明 |
|------|------|
| `services/url_whitelist.py` | URL 白名单定义和 `validate_fetch_url()` 实现 |
| `services/safety_service.py` | `_RESEARCH_SUBQUESTION_BLOCKLIST` 和提示注入防护 |
| `services/external_search_provider.py` | Provider 协议（含 `supports_web_search`/`supports_page_fetch`） |
| `docs/EXTERNAL_ACADEMIC_SEARCH_PLAN.md` | 学术搜索威胁模型（P3-01 制定，P6-05 扩展） |
