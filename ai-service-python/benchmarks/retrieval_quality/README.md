# 检索质量基准（retrieval_quality）

测本地 RAG 的**跨语言召回质量**：用中文提问检索英文论文语料，看能否命中正确论文。

这个基准存在的直接原因是一次实测发现：多语言小模型（`intfloat/multilingual-e5-small`，
384 维）在纯英文语料上处理中文查询时，top-1 结果不是随机错，而是**系统性坍缩到同一篇
论文**——10 个中文查询有 7 个 top-1 落在同一篇仅占库 15% chunk 的论文上，而语义等价的
英文查询 6/6 命中 6 篇不同论文。修复手段是查询侧中→英改写（`core/query_rewriter.py`）。

## 跑法

```bash
docker exec ai_service_python sh -lc "cd /app && python -m benchmarks.retrieval_quality.runner"
```

服务必须在运行（走 `POST /api/rag/retrieve`，不另起进程打开 chroma 持久化目录，
避免与服务进程争锁）。结果写入 `retrieval-quality-results.json`。

常用参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--base-url` | `http://127.0.0.1:8000` | 服务地址，也读 `PIXIU_AI_BASE_URL` |
| `--collection` | `literature_collection_v4_e5_small` | 用于剔除库中不存在的期望论文，也读 `PIXIU_RAG_COLLECTION` |
| `--db-path` | `/app/chroma_data/chroma.sqlite3` | 只读打开，取库内论文清单 |
| `--top-k` | `5` | 每一路的召回条数 |

## 指标

跑三组查询：中文原句、中文句子的人工英文等价句、纯英文术语句。每组给出：

- **top1 / top3** —— 名义命中率。
- **effectiveTop1** —— 扣掉假阳性后的有效命中率。**这是应该看的数字。**
  当 top-1 分布判定为坍缩时，凡是"期望答案恰好等于坍缩目标"的命中都不可信：
  无论问什么都会返回那篇论文，命中只是撞上了。
- **collapseRatio / collapseTarget** —— top-1 众数的占比与目标。随机分布下 7 篇论文
  约 0.14；阈值 `COLLAPSE_RATIO = 0.4`，超过即判定坍缩并在输出里打警告。
- **bm25NonZero** —— BM25 路有非零命中的查询数。中文查询在英文语料上词汇完全不重叠，
  改写前恒为 0；改写后应恢复成有效补召回。
- **rewritten** —— 实际触发了跨语言改写的查询数。为 0 说明改写没生效
  （检查 `PIXIU_QUERY_REWRITE_ENABLED`，或语料被判定为中文）。

`skipped` 是期望论文不在当前 collection 里的 case 数，它们不计入分母。
换一批语料后这个数会变大，属正常——`fixtures.json` 用**标题关键词**而不是 pdf id
标注期望，所以只要新语料里有同主题论文就仍能复用。

## 改写开关的严格 A/B

`core/query_rewriter.py` 提供降级开关 `PIXIU_QUERY_REWRITE_ENABLED`（默认开）。
要对比改写前后的差异，在 `docker-compose.yml` 的 ai-service 环境里设成 `0`、
重建容器跑一遍，再设回 `1` 跑一遍，比较两份 `retrieval-quality-results.json`
的 `metrics.chinese`：

```bash
docker exec -e PIXIU_QUERY_REWRITE_ENABLED=0 ai_service_python \
  sh -lc "cd /app && python -m benchmarks.retrieval_quality.runner --output /app/benchmarks/retrieval_quality/rewrite-off.json"
```

注意开关在**服务进程**里读取，用 `docker exec -e` 只影响 benchmark 进程本身、
不影响服务行为；要真正关掉服务侧的改写，必须改 compose 环境后重建容器。

## A/B 结果文件

仓库里留了两份结果，是同一份 `fixtures.json`、同一批语料（7 篇 3DGS 论文 / 352 chunk）、
只切换 `PIXIU_QUERY_REWRITE_ENABLED` 跑出来的严格对照：

| 文件 | 开关 | 含义 |
| --- | --- | --- |
| `rewrite-off-results.json` | `0` | 改写关闭，即改动前的基线行为 |
| `rewrite-on-results.json` | `1` | 改写开启，即当前默认行为 |

两份文件的 `metrics.chinese` 对比：

| 指标 | 改写关 | 改写开 |
| --- | --- | --- |
| top1（名义） | 5/10 | 10/10 |
| **effectiveTop1** | **3/10** | **10/10** |
| top3 | 6/10 | 10/10 |
| bm25NonZero | 0/10 | 10/10 |
| collapseRatio | 0.7（MVSplat） | 0.2（未判定坍缩） |
| rewritten | 0/10 | 10/10 |

同一次运行里的 `metrics.chineseEnglishEquivalent`（人工英文等价句）两轮都是 10/10，
说明改写后的中文查询已经达到人工标注的跨语言上限；`metrics.english` 两轮都是 6/6
且 `rewritten` 为 0/6，说明纯英文查询没有被误改写、无回归。

重跑时记得用 `--output` 指定新文件名，否则会覆盖 `retrieval-quality-results.json`
这个默认名——它不在仓库里，是本地临时产物。

两份文件的 `measuredAt` 里 off 比 on 晚十几分钟，因为第一份 off 结果写在容器可写层的
`/tmp` 下，下一次重建容器时被清空，重跑了一次才落到 bind mount 里。两轮针对的是同一个
collection、同一份代码，只差开关，所以重跑不影响对照成立（重跑后数字与第一次一致）。
这也是个教训：benchmark 产物要直接写到 bind mount 路径，不要先放 `/tmp`。

## 产品可见层的补充观测（chat 路径）

上面的 A/B 测的是检索层（`/api/rag/retrieve`），输入查询固定、可重复。用户实际看到的是
`/api/chat` 回答下面的引用列表（`ChatPanel.tsx` 渲染 `rag_sources`），这里多一层
**LLM 查询规划**（`services/query_service.rewrite_academic_query`），它自己就可能把中文
问题转成英文。实测（4 个中文问题，只切开关各跑一次）：

| 问题 | 规划后的 rewritten | 引用来源（关） | 引用来源（开） |
| --- | --- | --- | --- |
| 锚点高斯自适应生长与剪枝 | 中文 | MVSplat×2, 3DGS×2, **Scaffold-GS×1** | **Scaffold-GS×5** |
| 球面全景等距柱状投影畸变 | 中文 | 3DGS×3, MVSplat×1, **SPaGS×1** | **SPaGS×5** |
| 动态场景时间变形场与正则化 | 中文 | **MVSplat×3**, 4DGS×2 | **4DGS×2**, 3DGS/MVSplat/pixelSplat 各1 |
| 前馈式新视角合成代价体积 | **英文** | MVSplat×5 | MVSplat×5（无变化） |

两个结论：

1. 关闭时 top-1 又全部坐实在 MVSplat 这个吸引子上，且正确论文在 5 条引用里只占 1–2 条；
   开启后正确论文占满前排。
2. **当规划器已经输出英文时，改写不会触发也不应触发**（第 4 行）。所以产品层的收益
   比检索层的 3/10 → 10/10 要小，具体取决于规划器这一次是否自己译成了英文。

### 问答层的差异比命中率隐蔽

补测了回答正文与 `retrievalJudge`（4 问 × 开关各一轮），发现三个容易误判的点：

- **`verdict` 测不出差异**：两轮 4/4 全是 `CORRECT`，confidence 都在 0.86–0.92。
  因为即使证据里只有 1 条来自正确论文，LLM 也能靠自身先验把答案补完。所以
  不要拿 verdict 当检索质量的信号。
- **真正干净的信号是 `judgeReason` 的文本**：中文那 3 问 3/3 翻转——关闭时是
  “证据数量、文本长度和关键词覆盖整体足够”（只能靠“字数够”论证），开启后是
  “检索结果与问题高度相似，可支撑回答”（靠相关性论证）。第 4 问（英文）两轮完全一致。
- **回答长度与免责声明数量都不是信号**：关闭时回答有时反而更长（要先铺陈先验知识
  再声明证据缺口），免责句数量也不单调。差异在**内容归属**：关闭时模型用教科书式泛论
  填充，甚至会从证据里引一个跟问题无关的公式；开启后给出的是论文自己的算法与符号。

另：`sentenceSourceMap` 两轮都是 0 条，与改写无关。`build_sentence_source_map`
（`services/evidence_service.py`）在证据项缺 `sourceId` 或抽不出引用词时直接返回空列表，
前端 `ChatPanel.tsx` 的句级引用标注因此拿不到数据。根因未挖。

这一组没归入 runner，因为规划器是 LLM、跨跑不确定，做不了可重复基准；上面的数字是
单次观测，只用于说明量级和边界，不要当回归阈值用。要可重复的结论看上面两份 JSON。

## 历史基线

`fixtures.json` 的 `baseline` 段记录了改写上线前（2026-09-13）的实测值：
中文名义 top-1 5/10、有效 3/10、坍缩目标 MVSplat 占 7/10、BM25 非零 0/10、
英文 6/6。每次重跑都会把 baseline 一并写进结果文件，便于纵向对比。
