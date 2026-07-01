# P5-02 沙箱技术 Benchmark

## 结论

2026-07-01 在 Windows 11、Python 3.13.9、Docker Engine 29.5.3 环境执行固定安全探针后，最终决策为 `continue_to_p5_03`，选择加固 Docker Linux 容器作为后续建模候选。Windows Job Object 不能提供无网络、宿主文件隔离和只读输入保证，因此淘汰。

本结论不授权 Worker、执行 API、工具注册、前端入口或任何通用 Python/Shell 能力。完整机器可读结果见 `ai-service-python/benchmarks/code_sandbox/benchmark-results.json`。

## 候选与固定边界

| 候选 | 隔离方式 | 结果 |
| --- | --- | --- |
| 加固 Docker Linux 容器 | 非 root、只读根文件系统、只读输入、tmpfs 输出、无网络、capabilities 清空、`no-new-privileges`、seccomp、CPU/内存/PID/墙钟限制 | 合格：全部 11 项强制探针通过，任务后无残留容器 |
| Windows Job Object | Job Object 进程数、内存、墙钟和进程树终止限制 | 不合格：允许创建 socket、读取宿主 canary、改写输入副本 |

固定配额为 5 秒墙钟、1 CPU、128 MiB 内存、32 PID、1 MiB stdout、16 MiB tmpfs、1 MiB 输入。配额只用于 benchmark，不构成生产配置。

## 实测探针

- 正常 CSV 由固定 Python 标准库脚本生成有界 JSON。
- 提示/公式注入、路径文本、畸形 CSV 和超长字段只作为数据读取，不执行其中内容。
- 安全探针检查 socket 创建、宿主 canary、输入改写、根文件系统写入、子进程、CPU、内存、stdout 洪泛和任务后清理。
- Windows 候选通过正常/恶意输入、临时输出、子进程限制、资源限制和临时目录清理，但未通过网络、宿主文件和只读输入门槛。
- Docker 候选通过正常/恶意输入、socket 禁止、宿主 canary 隔离、只读输入/根文件系统、子进程禁止、CPU/内存/stdout 上限和可靠清理。实测镜像 ID 为 `sha256:c978142193ccdaa88f63356daa2b0d9c64fdc6de933c643d7cd47286160fdb1e`。

## 复现

在 `ai-service-python` 目录运行：

```powershell
python -m pytest tests/test_code_sandbox_benchmark.py -q
python -m benchmarks.code_sandbox.benchmark --live
```

第二条命令仅运行固定本地探针，不接受用户代码、路径、URL 或脚本参数。Docker 不可用、镜像构建失败或清理失败都必须封闭失败并返回 `stop_p5`；仅 Docker 全部门槛通过时返回 `continue_to_p5_03`。

## 已知边界

- 本次不评估 Windows containers、gVisor、Hyper-V VM 或云端沙箱。
- `continue_to_p5_03` 只允许继续定义 artifact、job、approval、audit 和 output 模型，不授权生产 Worker、API 或工具。
- benchmark 结果不证明容器可抵御未知内核或运行时逃逸漏洞。
