#!/usr/bin/env python3
"""sync_from_api.py — 从 BizyAir API 调用记录反向同步到本地 JSONL + 云端 Worker。

解决核心问题：Agent 通过 curl 直接调 API 时绕过了 task_logger hook，
导致大量任务丢失。此脚本从 API 的 mycalls 接口拉取真实记录，补齐本地日志。

用法：
  python3 scripts/sync_from_api.py              # 只同步到本地 JSONL
  python3 scripts/sync_from_api.py --push        # 同步后推送到云端
  python3 scripts/sync_from_api.py --pages 3     # 拉最近 3 页（每页 50）
"""
from __future__ import annotations
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import api
import task_logger


def fetch_mycalls_pages(key: str, pages: int = 3, page_size: int = 50) -> list[dict]:
    """从 BizyAir API 拉取调用记录。"""
    all_records = []
    base_url = "https://api.bizyair.cn/x/v1/modelzoo/mycalls"
    for page in range(1, pages + 1):
        url = f"{base_url}?current={page}&page_size={page_size}"
        result = api.safe_request_json(
            "POST", url, key,
            payload={"call_type": "trd_api_record"},
        )
        data = (result.get("data") or {}).get("data") or {}
        items = data.get("list") or []
        if not items:
            break
        all_records.extend(items)
    return all_records


def api_record_to_task_record(r: dict) -> dict:
    """把 API 调用记录转成 task_logger 格式。"""
    # 解析时间
    created_at = r.get("created_at", "")
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        unix_ts = int(dt.timestamp())
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S+0800")
    except (ValueError, TypeError):
        unix_ts = 0
        timestamp = created_at

    request_id = r.get("request_id", "")
    status = r.get("status", "Unknown")
    outputs = []

    # 提取 prompt 和完整提交参数
    request_params = r.get("request_params") or {}
    input_params = r.get("input_params") or {}

    # prompt 优先从 request_params 取（API 直出），fallback 到 input_params
    prompt = ""
    if isinstance(request_params, dict):
        prompt = request_params.get("prompt") or request_params.get("text") or ""
    if not prompt and isinstance(input_params, dict):
        prompt = input_params.get("prompt") or input_params.get("text") or ""

    # 合并 extra_params（提交参数快照）
    extra_params = {}
    if isinstance(request_params, dict) and request_params:
        extra_params.update(request_params)
    if isinstance(input_params, dict) and input_params:
        for k, v in input_params.items():
            if k not in extra_params:
                extra_params[k] = v

    usage = r.get("usage") or {}
    charge = usage.get("charge_amount")

    return {
        "timestamp": timestamp,
        "unix_ts": unix_ts,
        "request_id": request_id,
        "task_id": None,
        "source": "modelzoo",
        "model": r.get("endpoint", ""),
        "endpoint": r.get("endpoint", ""),
        "app_id": r.get("trd_api_node_name", ""),
        "prompt": prompt,
        "status": status,
        "outputs": outputs,
        "error": None,
        "charge_amount": charge,
        "extra_params": extra_params if extra_params else None,
        "sync_source": "api_mycalls",
    }


def enrich_with_details(key: str, records: list[dict]) -> list[dict]:
    """对每条记录查详情，补充 outputs（不覆盖已提取的 prompt）。"""
    import modelzoo
    for r in records:
        request_id = r.get("request_id", "")
        if not request_id:
            continue
        # 如果 extra_params 还没填满，补全 input_params
        has_extra = bool(r.get("extra_params"))
        try:
            detail = modelzoo.query_task(key, request_id)
            data = (detail.get("data") or {}).get("data") or detail.get("data") or {}
            # 补充 outputs
            outputs_data = data.get("outputs") or {}
            for media_type in ("texts", "images", "videos", "audios"):
                for url in (outputs_data.get(media_type) or []):
                    r["outputs"].append({"type": media_type, "url": url})
            # 补充 extra_params（input_params 快照）
            if not has_extra:
                input_params = data.get("input_params") or {}
                if isinstance(input_params, dict) and input_params:
                    r["extra_params"] = input_params
            # 更新状态
            if data.get("status"):
                r["status"] = data["status"]
        except Exception:
            pass  # 查不到就用原始数据
    return records


def sync(pages: int = 3, enrich: bool = True) -> list[dict]:
    """主同步流程。"""
    key = api.require_api_key(None)
    print(f"📡 从 BizyAir API 拉取 {pages} 页调用记录...", file=sys.stderr)
    api_records = fetch_mycalls_pages(key, pages=pages)
    print(f"  拉到 {len(api_records)} 条 API 记录", file=sys.stderr)

    # 转换格式
    task_records = [api_record_to_task_record(r) for r in api_records]

    # 补充详情（prompt + outputs）
    if enrich:
        print(f"🔍 补充详情（prompt + outputs）...", file=sys.stderr)
        task_records = enrich_with_details(key, task_records)

    # 读取本地已有的 request_id 集合，避免重复
    existing = task_logger.read_task_log(limit=5000)
    existing_ids = {r.get("request_id") for r in existing if r.get("request_id")}

    # 只写入新增的（直接写 JSONL，保留 API 的时间戳）
    new_count = 0
    log_path = task_logger._log_file_path()
    for r in task_records:
        if r["request_id"] and r["request_id"] not in existing_ids:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                new_count += 1
            except Exception:
                pass  # 静默失败

    print(f"  新增 {new_count} 条，跳过 {len(task_records) - new_count} 条已存在", file=sys.stderr)
    return task_records


def push_to_cloud(records: list[dict], worker_url: str, token: str = "") -> dict:
    """推送到 Cloudflare Worker。"""
    # 合并本地所有记录
    all_records = task_logger.read_task_log(limit=5000)
    # 去重（按 request_id，保留最新的）
    seen = {}
    for r in all_records:
        rid = r.get("request_id") or r.get("task_id") or ""
        if rid:
            seen[rid] = r
        else:
            seen[f"_anon_{len(seen)}"] = r
    unique = list(seen.values())
    unique.sort(key=lambda r: r.get("unix_ts", 0), reverse=True)

    url = worker_url.rstrip("/") + "/api/tasks"
    if token:
        url += f"?token={token}"
    payload = json.dumps(unique, ensure_ascii=False)
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", url,
         "-H", "Content-Type: application/json",
         "-d", payload],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.decode()}
    return json.loads(result.stdout.decode())


def main():
    import argparse
    p = argparse.ArgumentParser(description="从 BizyAir API 同步调用记录")
    p.add_argument("--pages", type=int, default=3, help="拉取页数（每页 50）")
    p.add_argument("--push", action="store_true", help="同步后推送到云端")
    p.add_argument("--worker-url", default="https://bizyair.1986318.xyz")
    p.add_argument("--token", default="")
    p.add_argument("--no-enrich", action="store_true", help="跳过详情查询（快但缺 prompt）")
    args = p.parse_args()

    records = sync(pages=args.pages, enrich=not args.no_enrich)

    if args.push:
        print(f"🚀 推送到 {args.worker_url}...", file=sys.stderr)
        result = push_to_cloud(records, args.worker_url, args.token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"ok": True, "synced": len(records)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
