#!/usr/bin/env python3
"""push_tasks.py — 将本地任务日志推送到 Cloudflare Worker。

用法（Agent 自动调用）：
  python3 scripts/push_tasks.py https://xxx.workers.dev
  python3 scripts/push_tasks.py https://xxx.workers.dev --token YOUR_TOKEN
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import task_logger


def lsky_to_https_proxy(url: str, viewer_base: str) -> str:
    """将 Lsky HTTP URL 转换为 viewer 上的 HTTPS 代理 URL（解决混合内容问题）。

    - 输入：http://11.tcp.cpolar.top:14531/uploads/2026/06/06/abc.png
    - 输出：https://bizyair.1986318.xyz/proxy?url=http%3A%2F%2F11.tcp.cpolar.top%3A14531%2Fuploads%2F2026%2F06%2F06%2Fabc.png
    - CF Worker 第一次拉 Lsky 慢，第二次命中 30 天缓存秒开
    """
    if not url or not url.startswith("http://"):
        return url
    if "/proxy?url=" in url:
        return url  # 已经是代理 URL
    base = viewer_base.rstrip("/")
    return f"{base}/proxy?url={urllib.parse.quote(url, safe='')}"


def rewrite_lsky_urls(records: list, viewer_base: str) -> list:
    """遍历 records，把所有 HTTP 输出 URL 替换为 viewer 代理 URL。"""
    rewritten = 0
    for r in records:
        for o in r.get("outputs", []):
            url = o.get("url", "")
            if not url:
                continue
            new = lsky_to_https_proxy(url, viewer_base)
            if new != url:
                o["url"] = new
                # 保留原 URL 备查
                o["_original_url"] = url
                rewritten += 1
    if rewritten:
        print(f"  → 转换 {rewritten} 个 HTTP URL 为 viewer HTTPS 代理", file=sys.stderr)
    return records


def push(base_url: str, token: str = "", viewer_base: str | None = None) -> dict:
    records = task_logger.read_task_log(limit=1000)
    if not records:
        return {"ok": True, "message": "no records to push", "count": 0}

    # 自动推导 viewer_base（如果未指定）
    if not viewer_base:
        # 移除 .workers.dev 后缀的子域作为 viewer 域名候选
        viewer_base = os.environ.get("BIZYAIR_VIEWER_BASE", "")
        if not viewer_base:
            from urllib.parse import urlparse
            p = urlparse(base_url)
            # 如果推送到 bizyair-task-viewer.violinpearson.workers.dev
            # 推 viewer 用 https://bizyair.1986318.xyz
            viewer_base = "https://bizyair.1986318.xyz"

    records = rewrite_lsky_urls(records, viewer_base)

    url = base_url.rstrip("/") + "/api/tasks"
    if token:
        url += f"?token={token}"

    payload = json.dumps(records, ensure_ascii=False)

    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", url,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.decode("utf-8", errors="replace")}
        return json.loads(result.stdout.decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="推送任务日志到 Cloudflare")
    parser.add_argument("url", help="Worker URL, e.g. https://bizyair-tasks.xxx.workers.dev")
    parser.add_argument("--token", default="", help="Bearer token (if set)")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--viewer-base", default=os.environ.get("BIZYAIR_VIEWER_BASE", "https://bizyair.1986318.xyz"),
                        help="viewer 域名，用于把 HTTP Lsky URL 转为 HTTPS 代理 URL")
    args = parser.parse_args()

    result = push(args.url, args.token, viewer_base=args.viewer_base)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
