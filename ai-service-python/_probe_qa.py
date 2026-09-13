"""对比 /api/chat 在改写开/关下的问答表现。临时脚本，跑完即删。

抓三类信号：
1. retrievalJudge —— 服务自己对"证据是否够回答"的判定（verdict/confidence/shouldRetry）；
2. rag_sources —— 引用来源的论文分布；
3. message —— 回答全文，用于人工比对事实归属是否正确。

用法：python _probe_qa.py <on|off>
"""
import json
import os
import sys
import time
import urllib.request

QUESTIONS = [
    ("锚点高斯是如何自适应生长和剪枝的", "Scaffold-GS"),
    ("球面全景等距柱状投影的畸变如何处理", "SPaGS"),
    ("动态场景的时间变形场与正则化怎么设计", "4DGS"),
    ("前馈式新视角合成怎么用代价体积重建高斯", "MVSplat"),
]

LABELS = [
    ("scaffold-gs", "Scaffold-GS"),
    ("mvsplat", "MVSplat"),
    ("pixelsplat", "pixelSplat"),
    ("4d gaussian", "4DGS"),
    ("real-time radiance", "3DGS"),
    ("spherical panorama", "SPaGS"),
]


def short(title):
    low = str(title).lower()
    for needle, label in LABELS:
        if needle in low:
            return label
    return str(title)[:24]


tag = sys.argv[1] if len(sys.argv) > 1 else "probe"
rows = []
for question, expect in QUESTIONS:
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/chat",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.loads(resp.read().decode())
    elapsed = time.time() - started

    plan = data.get("queryPlan") or {}
    judge = data.get("retrievalJudge") or {}
    sources = data.get("rag_sources") or []
    titles = [short((s.get("metadata") or {}).get("title") or s.get("title") or "?") for s in sources if isinstance(s, dict)]
    rewritten = str(plan.get("rewritten") or "")

    rows.append(
        {
            "question": question,
            "expect": expect,
            "rewritten": rewritten,
            "rewrittenIsChinese": any("\u4e00" <= c <= "\u9fff" for c in rewritten),
            "verdict": judge.get("verdict"),
            "confidence": judge.get("confidence"),
            "shouldRetry": judge.get("shouldRetry"),
            "judgeReason": judge.get("reason"),
            "missingAspects": judge.get("missingAspects"),
            "sourceCount": len(titles),
            "sourceLabels": titles,
            "top1Correct": bool(titles) and titles[0] == expect,
            "expectShare": round(titles.count(expect) / len(titles), 2) if titles else 0.0,
            "sentenceMapCount": len(data.get("sentenceSourceMap") or []),
            "elapsedSeconds": round(elapsed, 1),
            "answer": str(data.get("message") or ""),
        }
    )

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_qa_{tag}.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(rows, fh, ensure_ascii=False, indent=2)

for row in rows:
    print("-" * 64)
    print("Q:", row["question"], "| 期望:", row["expect"])
    print("  rewritten:", row["rewritten"][:70], "| 中文:", row["rewrittenIsChinese"])
    print("  verdict:", row["verdict"], "| conf:", row["confidence"], "| shouldRetry:", row["shouldRetry"])
    print("  reason:", str(row["judgeReason"])[:110])
    print("  missing:", row["missingAspects"])
    print(f"  sources({row['sourceCount']}):", row["sourceLabels"], "| top1正确:", row["top1Correct"], "| 期望占比:", row["expectShare"])
    print("  句级引用数:", row["sentenceMapCount"], "| 耗时:", row["elapsedSeconds"], "s | 答案字数:", len(row["answer"]))
print("written:", path)
