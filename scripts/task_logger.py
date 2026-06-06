"""task_logger.py — BizyAir 任务调用日志。

每次 API 调用（创建任务）后，把 request_id + 输出 URL + 元信息追加写入 JSONL 文件。
被 dispatch.py（ModelZoo 路径）和 app.py（webapp 路径）调用。

设计原则：
  - 零依赖：只 import json / time / pathlib，不依赖 skill 内部其他模块
  - 防崩溃：写入失败时 stderr 打警告，绝不抛异常影响主流程
  - 追加写入：JSONL 格式，每行一条独立 JSON，不怕并发追加损坏（O_APPEND）
  - 存储位置：paths.resolve_runtime_root() / task_log.jsonl（skill 目录内，无权限问题）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _log_file_path() -> Path:
    """日志文件路径。

    优先尝试 skill 目录内的 .tmp/bizyair/task_log.jsonl（非 sandbox 环境下可用），
    如果不可写则回退到 /tmp/bizyair_task_log.jsonl（sandbox 内也能写）。
    """
    from paths import resolve_runtime_root
    preferred = resolve_runtime_root() / "task_log.jsonl"
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        test = preferred.parent / "._write_test"
        test.write_text("ok")
        test.unlink()
        return preferred
    except (OSError, PermissionError):
        return Path("/tmp/bizyair_task_log.jsonl")


def log_task(
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    source: str,  # "modelzoo" | "webapp"
    model: str | None = None,
    endpoint: str | None = None,
    app_id: str | None = None,
    prompt: str | None = None,
    status: str = "unknown",
    outputs: list[dict] | None = None,
    error: str | None = None,
    extra: dict | None = None,
    extra_params: dict | None = None,
) -> dict:
    """记录一条任务日志，返回写入的记录 dict。

    outputs 格式: [{"type": "images", "url": "https://..."}, ...]
    extra_params: 原始提交参数（prompt、resolution、steps、style 等）
    """
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "unix_ts": int(time.time()),
        "request_id": request_id,
        "task_id": task_id,
        "source": source,
        "model": model,
        "endpoint": endpoint,
        "app_id": app_id,
        "prompt": (prompt or "")[:500] if prompt else None,
        "status": status,
        "outputs": outputs or [],
        "error": error,
    }
    if extra:
        record["extra"] = extra
    if extra_params:
        # 只存有用的提交参数，不存整个 argparse.Namespace
        safe = {k: v for k, v in extra_params.items()
                if not k.startswith('_') and k not in ('func', 'called_args')}
        record["extra_params"] = safe

    try:
        log_path = _log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        print(
            f"[task_logger] WARNING: failed to write task log: {exc}",
            file=sys.stderr,
        )

    return record


def read_task_log(*, limit: int = 100) -> list[dict]:
    """读取最近的 N 条任务日志（倒序，最新在前）。"""
    try:
        log_path = _log_file_path()
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
        return records
    except Exception:
        return []
