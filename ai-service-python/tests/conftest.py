"""Shared pytest fixtures and configuration for the Pixiu AI service test suite.

Usage: fixtures in this module are auto-discovered by pytest — no explicit
import needed in individual test files.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so that "from services.xxx import ..."
# resolves correctly regardless of the working directory.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture(autouse=True)
def reset_tool_registry_after_test():
    """Reset the global tool registry so each test starts with a clean state."""
    yield
    from services.tool_registry import reset_tool_registry

    try:
        reset_tool_registry()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def isolated_llm_cache(monkeypatch):
    """每个测试用独立的内存 LLM 缓存。

    缓存默认落在 data/llm_cache.sqlite3（持久化文件，且在容器挂载卷内），
    不隔离它会带来两个后果：

    1. 套件不可重复运行 —— 第一次跑把 mock 出来的响应写进缓存，第二次跑时
       DeepSeekLLM._call 命中缓存并提前 return，永远走不到 invoke() 里的
       record_counter("llmCalls")，于是断言 llmCalls == 1 的测试必然失败
       （实测复现：test_research_task_service.py 首跑 passed、二跑 failed，
       加 PIXIU_LLM_CACHE_PATH=:memory: 后又 passed）。
    2. 测试数据污染生产缓存文件。
    """
    monkeypatch.setenv("PIXIU_LLM_CACHE_PATH", ":memory:")

    from services import llm_cache

    # get_llm_cache() 是模块级单例，只改环境变量不重置单例的话，
    # 先前测试建好的文件型实例会继续被复用。
    monkeypatch.setattr(llm_cache, "_cache", None)
    yield
    monkeypatch.setattr(llm_cache, "_cache", None)
