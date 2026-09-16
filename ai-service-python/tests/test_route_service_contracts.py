"""路由层引用契约：routes/ 里每个 `模块.函数(...)` 都必须真实存在。

实测揭出来的破损：reading_routes 的 /socratic-questions、/socratic-session/start、
/socratic-session/answer、/explain-term 四个端点全都调用 chat_service.<函数>，
而这四个函数在 chat_service 里根本不存在 —— 它们分别住在 socratic_service 与
term_explanation_service。前端 api.ts 确实在调 /socratic-session/start 与
/socratic-session/answer，所以"引导式学习"整个功能一请求就 AttributeError -> 500，
"术语解释"同样全灭。

这类破损常规单测抓不到：service 自己的测试直接 import service、从不经过路由，
而路由层一个测试都没有。这里用 AST 静态解析 routes/ 下对自家模块的属性引用并逐个
核对，刻意不 import 任何业务模块 —— import services 会连带加载嵌入模型，
既慢又有副作用，静态解析同样能给出确定结论。
"""

import ast
import tempfile
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = SERVICE_ROOT / "routes"

# 只核对自家代码；fastapi/pydantic 这类三方库的属性不在契约范围内。
OWN_PACKAGES = frozenset({"services", "core", "llm", "rag", "schemas", "routes"})


def _module_file(dotted: str) -> Path | None:
    """把点号路径解析成 .py 文件，包则解析到 __init__.py。"""
    candidate = SERVICE_ROOT.joinpath(*dotted.split("."))
    as_file = candidate.with_suffix(".py")
    if as_file.is_file():
        return as_file
    as_package = candidate / "__init__.py"
    if as_package.is_file():
        return as_package
    return None


def _collect_top_level(node: ast.AST, names: set[str]) -> None:
    """收集一个语句在模块顶层绑定的名字。

    要递归进 If/Try：reading_routes 自己就用了 `try: from fastapi import ...
    except ModuleNotFoundError: from tests.fastapi_stubs import ...`，
    两条分支绑定的都是真实的顶层名字。
    """
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        names.add(node.name)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            names.add(node.target.id)
    elif isinstance(node, ast.Import | ast.ImportFrom):
        for alias in node.names:
            if alias.name != "*":
                names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.If):
        for child in [*node.body, *node.orelse]:
            _collect_top_level(child, names)
    elif isinstance(node, ast.Try):
        branches = [*node.body, *node.orelse, *node.finalbody]
        for handler in node.handlers:
            branches.extend(handler.body)
        for child in branches:
            _collect_top_level(child, names)
    elif isinstance(node, ast.With | ast.AsyncWith):
        for child in node.body:
            _collect_top_level(child, names)


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        _collect_top_level(node, names)
    return names


def _imported_locals(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """本地名 -> (来源模块, 被导入的名字)。只收自家包的导入。"""
    locals_map: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in OWN_PACKAGES:
            for alias in node.names:
                if alias.name != "*":
                    locals_map[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in OWN_PACKAGES:
                    locals_map[alias.asname or alias.name] = ("", alias.name)
    return locals_map


def _resolve_target(module: str, name: str) -> tuple[str, str] | None:
    """判定本地名指向子模块还是模块内属性，返回 (待检查的文件点号路径, 属性名或 "")。

    `from services import chat_service` 里 chat_service 是子模块；
    `from services.chat_service import chat` 里 chat 是属性。
    靠文件系统判定，不需要 import。
    """
    dotted = f"{module}.{name}" if module else name
    if _module_file(dotted) is not None:
        return (dotted, "")
    if module and _module_file(module) is not None:
        return (module, name)
    return None


def _route_reference_problems(routes_dir: Path = ROUTES_DIR) -> list[str]:
    problems: list[str] = []
    for route_file in sorted(routes_dir.glob("*.py")):
        tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
        locals_map = _imported_locals(tree)

        # 本地名 -> 它指向的模块文件与该文件的顶层名集合
        resolved: dict[str, tuple[Path, set[str], str]] = {}
        for local, (module, name) in locals_map.items():
            target = _resolve_target(module, name)
            if target is None:
                problems.append(f"{route_file.name}: 无法定位导入 {module}.{name}".replace(".:", ":"))
                continue
            target_dotted, attr = target
            target_path = _module_file(target_dotted)
            assert target_path is not None
            resolved[local] = (target_path, _top_level_names(target_path), attr)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            base = node.func.value
            if not isinstance(base, ast.Name) or base.id not in resolved:
                continue
            target_path, names, attr = resolved[base.id]
            if "__getattr__" in names:
                # 模块用 __getattr__ 做动态转发，静态检查看不见它的属性，跳过避免误报。
                continue
            called = node.func.attr
            if attr:
                # 本地名本身是属性（如 from services.x import helper），再取它的属性
                # 属于对象方法调用，不在本契约范围内。
                if attr not in names:
                    problems.append(
                        f"{route_file.name}:{node.lineno} 导入的 {target_path.stem}.{attr} 不存在"
                    )
                continue
            if called not in names:
                problems.append(
                    f"{route_file.name}:{node.lineno} 调用了 {target_path.stem}.{called}()，"
                    f"但该模块里没有这个名字"
                )
    return problems


class RouteServiceContractTests(unittest.TestCase):
    def test_every_route_call_target_exists(self):
        problems = _route_reference_problems()
        self.assertEqual(problems, [], "\n".join(problems))

    def test_scanner_actually_covers_the_reading_routes(self):
        """护栏自己也要被护栏：确认扫描器真的看到了 reading_routes 的那些端点。

        扫描器若因为解析规则写窄而漏掉整个文件，上面的测试会静默变绿 —— 那比没有
        测试更糟。这里钉住它确实检查了本轮修复涉及的两个模块。
        """
        route_file = ROUTES_DIR / "reading_routes.py"
        tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
        locals_map = _imported_locals(tree)
        self.assertIn("socratic_service", locals_map)
        self.assertIn("term_explanation_service", locals_map)
        self.assertIn("chat_service", locals_map)

        socratic_path = _module_file("services.socratic_service")
        self.assertIsNotNone(socratic_path)
        socratic_names = _top_level_names(socratic_path)
        for name in ("generate_socratic_questions", "start_socratic_session", "answer_socratic_question"):
            self.assertIn(name, socratic_names)

        # 反向确认：chat_service 里确实没有这些函数，所以旧路由必然 AttributeError。
        chat_names = _top_level_names(_module_file("services.chat_service"))
        for name in ("generate_socratic_questions", "start_socratic_session", "answer_socratic_question", "explain_term"):
            self.assertNotIn(name, chat_names)

        term_names = _top_level_names(_module_file("services.term_explanation_service"))
        self.assertIn("explain_term", term_names)

    def test_scanner_rejects_a_bogus_reference(self):
        """给扫描器喂一个已知坏的引用，确认它会报错而不是恒返回空列表。

        这是护栏的护栏：扫描规则一旦写窄（比如漏掉某种导入形式），上面那个测试会
        静默变绿，比没有测试更糟。所以在临时目录里造一个真的坏路由文件，
        断言扫描器必须报出它。
        """
        bogus = (
            "from services import chat_service\n"
            "from services.socratic_service import start_socratic_session\n"
            "\n"
            "def handler(request):\n"
            "    # 坏引用：chat_service 里没有这个函数\n"
            "    chat_service.generate_socratic_questions(request)\n"
            "    # 好引用：本地名是属性而非子模块，扫描器不该误报\n"
            "    start_socratic_session(request)\n"
            "    return chat_service.chat(request)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            routes_dir = Path(tmp)
            (routes_dir / "bogus_routes.py").write_text(bogus, encoding="utf-8")
            problems = _route_reference_problems(routes_dir)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("generate_socratic_questions", problems[0])
        # 真实 routes/ 必须干净，否则说明自检用的坏样本反而漏进了生产代码。
        self.assertEqual(_route_reference_problems(), [])


if __name__ == "__main__":
    unittest.main()
