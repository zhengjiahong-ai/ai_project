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

# DeepSeekLLM.invoke 的唯一网络出口是 requests.post(f"{base_url}/chat/completions")
# （llm/client.py:156）。按 URL 特征识别，避免波及外部检索等非 LLM 的 HTTP 测试。
_LLM_HTTP_MARKER = "/chat/completions"


class LiveLLMBlockedError(RuntimeError):
    """测试未打桩就想打真实 LLM 时抛出。

    刻意用 RuntimeError 而不是 requests.RequestException：生产代码里那些
    try/except Exception 的回退分支会立刻接住它并走确定性回退，用例因此
    毫秒级返回；而 RequestException 会被 invoke 归一化成 retryable=True 的
    LLMProviderError，万一将来加了重试退避就会把套件重新拖慢。
    """


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


@pytest.fixture(autouse=True)
def block_live_llm_http(request, monkeypatch):
    """默认切断真实 LLM 网络出口，让套件离线、可复现、且不会被 --timeout 杀掉。

    实测代价（同一份代码、同一批测试、同一台机器）：

    - 账户欠费时 DeepSeek 立刻回 402，全量回归 106 秒跑完，看上去一切正常；
    - 账户恢复后同一批测试跑了 18 分 58 秒，其中
      test_paper_writer::test_custom_title_is_used 单独跑要 57.82 秒，而 CI 命令行
      是 --timeout=60，只剩 2.2 秒余量 —— 全量回归时 CPU 被别的测试占用就越线
      被杀，报出一个与被测改动毫无关系的失败。

    根因是这两个文件完全没打桩、直连真 LLM：test_paper_writer.py 每个用例触发
    _llm_abstract + _llm_conclusion 两次调用（各带 20 秒 future 超时），
    LlmAcademicQueriesTests 每个用例一次。测试断言的全是结构与长度，从不断言
    LLM 写了什么，所以那些网络往返纯属浪费，还让结果随账户余额变化。

    切在 llm.client.requests.post 这一层是因为它已是本仓库既有的打桩靶点
    （test_offline_llm.py 6 处、test_offline_core_paths.py 4 处、
    test_research_task_service.py 1 处），测试内部的 patch 会正常覆盖本 fixture；
    fixture 模式与已经打桩 invoke 的路径根本走不到这里，不受影响。

    真需要活调用的测试用 @pytest.mark.live_llm 显式退出（并在 CI 里靠无 key
    自然跳过），默认一律离线。
    """
    if request.node.get_closest_marker("live_llm"):
        yield
        return

    from llm import client as llm_client

    real_post = llm_client.requests.post

    def _guarded_post(url, *args, **kwargs):
        if _LLM_HTTP_MARKER in str(url):
            raise LiveLLMBlockedError(
                f"测试试图请求真实 LLM（{url}）。请打桩 llm.client.requests.post，"
                "或给该测试加 @pytest.mark.live_llm 显式声明它需要活调用。"
            )
        return real_post(url, *args, **kwargs)

    monkeypatch.setattr(llm_client.requests, "post", _guarded_post)
    yield
