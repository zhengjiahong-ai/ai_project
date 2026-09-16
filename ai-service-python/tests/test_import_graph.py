"""模块导入图回归：critical_reading 必须能被单独导入。

这不是风格洁癖，是一条曾经真实存在的缺陷。改动前的形状是：

    critical_reading.py  顶部  from services.analysis_service import (19 个名字)
    analysis_service.py  第 970 行  from services.critical_reading import (6 个名字)

两条边互为前提，只有“先导 analysis_service”这一个顺序能活。后果是
`import services.critical_reading` 单独跑必报
ImportError: cannot import name '_attach_numeric_evidence_to_claims' from
partially initialized module，于是本模块无法被单独单测，每个探测脚本都得
先写一行与任务无关的 `import services.analysis_service` 才不炸；而
tests/test_citation_responses.py 能用，纯粹是因为 `from services import
analysis_service, chat_service, critical_reading` 的字母序碰巧把
analysis_service 排在了前面 —— 换个人改一下导入顺序就全红。

修好的形状是：19 个名字里 17 个其实只有 critical_reading 在用，搬回它自己
（其中 3 个本来就在 core.pdf_quality，改成直接从那里取）；真正两边共享的
_merge_evidence_lists / _deduplicate_evidence 下沉到只依赖 stdlib 的
services/evidence_service.py。于是只剩 analysis_service → critical_reading
这一条边，环消失。

第一条断言守源码（快、错误信息直接），第二条守运行时（证明不只是文本上
没有那行 import，而是真的能起来）。
"""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_READING = REPO_ROOT / "services" / "critical_reading.py"
ANALYSIS_SERVICE = REPO_ROOT / "services" / "analysis_service.py"


def _imported_modules(path: Path) -> set[str]:
    """取出一个文件里所有模块级 import 的模块名（含函数体内的延迟 import）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


class ImportGraphTests(unittest.TestCase):
    def test_critical_reading_does_not_import_analysis_service(self):
        """反向边一旦回来，环就回来，单独导入立刻炸。"""
        imported = _imported_modules(CRITICAL_READING)
        # 防空断言：解析失败或返回空集时，上面的 assertNotIn 会假绿。
        self.assertIn("services.evidence_service", imported)
        self.assertNotIn("services.analysis_service", imported)

    def test_analysis_service_still_depends_on_critical_reading(self):
        """正向边是设计意图：deep_analysis 要调那 6 个批判分析函数。

        一起断言是为了让"两边都不导入"这种把功能改没了的修法也失败。
        """
        self.assertIn("services.critical_reading", _imported_modules(ANALYSIS_SERVICE))

    def test_critical_reading_is_importable_in_a_fresh_process(self):
        """实证：干净解释器里单独导入本模块必须成功。

        必须在子进程里跑 —— 同进程内 pytest 早就把 analysis_service 导入了，
        sys.modules 里已有半成品也会让循环导入"看起来"正常，测不出真形状。
        """
        result = subprocess.run(
            [sys.executable, "-c", "import services.critical_reading"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"单独导入 services.critical_reading 失败：\n{result.stderr[-1200:]}",
        )


if __name__ == "__main__":
    unittest.main()
