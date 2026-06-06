#!/usr/bin/env python3
"""从 API 同步的 enriched 记录 + 本地 JSONL 日志 合并生成 index.html。
用法: python3 gen_viewer_from_enriched.py [--enriched /path/to/enriched.json] [--jsonl /path/to/log.jsonl]
"""
from __future__ import annotations
import json
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

ENRICHED_DEFAULT = "/tmp/bizyair_enriched_records.json"
JSONL_DEFAULT = "/tmp/bizyair_task_log.jsonl"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BizyAir 任务日志</title>
<style>
  :root {
    --bg: #0a0a0a; --card: #141414; --border: #262626;
    --text: #e5e5e5; --muted: #737373; --accent: #3b82f6;
    --success: #22c55e; --failed: #ef4444; --pending: #f59e0b;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  .header { padding: 32px 24px 16px; max-width: 1200px; margin: 0 auto; }
  .header h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }
  .header .subtitle { color: var(--muted); font-size: 13px; margin-top: 4px; }
  .header .stats { display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 16px; font-size: 13px; }
  .stat .num { font-size: 22px; font-weight: 700; }
  .stat .label { color: var(--muted); margin-top: 2px; }

  .filters { padding: 8px 24px 16px; max-width: 1200px; margin: 0 auto; display: flex; gap: 8px; flex-wrap: wrap; }
  .filter-btn { background: var(--card); border: 1px solid var(--border); color: var(--muted); border-radius: 8px; padding: 6px 14px; font-size: 13px; cursor: pointer; transition: all .15s; }
  .filter-btn:hover { border-color: var(--accent); color: var(--text); }
  .filter-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

  .timeline { padding: 0 24px 40px; max-width: 1200px; margin: 0 auto; }
  .task-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 10px; transition: border-color .15s; }
  .task-card:hover { border-color: #404040; }
  .task-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
  .task-id { font-family: "SF Mono", "Fira Code", monospace; font-size: 13px; color: var(--accent); }
  .task-time { font-size: 12px; color: var(--muted); }

  .status-badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
  .status-Success { background: rgba(34,197,94,.15); color: var(--success); }
  .status-Failed { background: rgba(239,68,68,.15); color: var(--failed); }
  .status-Running { background: rgba(59,130,246,.15); color: #60a5fa; }
  .status-AsyncSubmitted { background: rgba(245,158,11,.15); color: var(--pending); }
  .status-NoOutputs { background: rgba(239,68,68,.1); color: #f87171; }

  .task-body { display: flex; gap: 20px; align-items: flex-start; }
  .task-info { flex: 1; min-width: 0; }
  .task-prompt { font-size: 14px; line-height: 1.5; margin-bottom: 6px; word-break: break-word; }
  .task-meta { font-size: 12px; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
  .task-meta span { white-space: nowrap; }

  .extra-params { margin-top: 8px; }
  .extra-params summary { cursor: pointer; font-size: 12px; color: var(--accent); user-select: none; }
  .extra-params summary:hover { text-decoration: underline; }
  .extra-params table { width: 100%; border-collapse: collapse; margin-top: 4px; font-size: 12px; }
  .extra-params td { padding: 3px 8px; border-bottom: 1px solid var(--border); }
  .extra-params td:first-child { color: var(--muted); white-space: nowrap; width: 40%; }
  .extra-params td:last-child { color: var(--text); word-break: break-all; }

  .task-outputs { flex-shrink: 0; display: flex; flex-direction: column; align-items: center; }
  .output-thumb { width: 80px; height: 80px; border-radius: 8px; object-fit: cover; border: 1px solid var(--border); cursor: pointer; transition: transform .15s; }
  .output-thumb:hover { transform: scale(1.08); }
  .output-link { display: block; font-size: 11px; color: var(--accent); text-decoration: none; margin-top: 4px; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .error-msg { font-size: 12px; color: var(--failed); background: rgba(239,68,68,.08); border-radius: 6px; padding: 6px 10px; margin-top: 6px; }
  .empty { text-align: center; padding: 60px; color: var(--muted); font-size: 15px; }

  .lightbox { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.85); z-index: 999; align-items: center; justify-content: center; cursor: pointer; }
  .lightbox.open { display: flex; }
  .lightbox img { max-width: 90vw; max-height: 90vh; border-radius: 8px; }

  .no-output { width: 80px; height: 80px; border-radius: 8px; border: 1px dashed var(--border); display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 11px; text-align: center; padding: 4px; }

  .copy-btn { background: none; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 3px 8px; font-size: 11px; cursor: pointer; margin-left: 6px; }
  .copy-btn:hover { border-color: var(--accent); color: var(--text); }

  .search-bar { padding: 0 24px 16px; max-width: 1200px; margin: 0 auto; }
  .search-bar input { width: 100%; background: var(--card); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 10px 14px; font-size: 14px; outline: none; }
  .search-bar input:focus { border-color: var(--accent); }
</style>
</head>
<body>

<div class="header">
  <h1>BizyAir 任务日志</h1>
  <div class="subtitle" id="subtitle"></div>
  <div class="stats" id="stats"></div>
</div>

<div class="search-bar">
  <input type="text" id="searchInput" placeholder="搜索提示词、模型、request_id...">
</div>

<div class="filters" id="filters">
  <button class="filter-btn active" data-filter="all">全部</button>
  <button class="filter-btn" data-filter="Success">成功</button>
  <button class="filter-btn" data-filter="Failed">失败</button>
  <button class="filter-btn" data-filter="Running">进行中</button>
  <button class="filter-btn" data-filter="AsyncSubmitted">异步中</button>
</div>

<div class="timeline" id="timeline"></div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('open')">
  <img id="lightbox-img" src="">
</div>

<script>
const DATA = __RECORDS__;
let FILTER = 'all';
let SEARCH = '';

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function renderStats(records) {
  const total = records.length;
  const success = records.filter(r => r.status === 'Success').length;
  const failed = records.filter(r => r.status === 'Failed').length;
  const running = records.filter(r => r.status === 'Running').length;
  const outputs = records.reduce((s, r) => s + (r.outputs?.length || 0), 0);
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="num">${total}</div><div class="label">总任务</div></div>
    <div class="stat"><div class="num" style="color:var(--success)">${success}</div><div class="label">成功</div></div>
    <div class="stat"><div class="num" style="color:var(--failed)">${failed}</div><div class="label">失败</div></div>
    <div class="stat"><div class="num" style="color:#60a5fa">${running}</div><div class="label">进行中</div></div>
    <div class="stat"><div class="num">${outputs}</div><div class="label">产出文件</div></div>
  `;
}

function copyId(text) {
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = '已复制';
    setTimeout(() => btn.textContent = '复制', 1000);
  }).catch(() => {});
}

function renderTimeline(records, filter, search) {
  let filtered = records;
  if (filter !== 'all') filtered = filtered.filter(r => r.status === filter);
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter(r =>
      (r.prompt || '').toLowerCase().includes(q) ||
      (r.request_id || '').toLowerCase().includes(q) ||
      (r.model_name || r.model || r.app_id || '').toLowerCase().includes(q) ||
      (r.endpoint || '').toLowerCase().includes(q)
    );
  }

  const el = document.getElementById('timeline');
  if (!filtered.length) { el.innerHTML = '<div class="empty">暂无任务记录</div>'; return; }

  el.innerHTML = filtered.map(r => {
    const id = r.request_id || r.task_id || '-';
    const model = r.model_name || r.model || r.app_id || '-';
    const source = r.source === 'modelzoo' ? 'ModelZoo' : 'WebApp';
    const ts = r.created_at || (r.timestamp || '').replace('T', ' ').replace(/\+\d+$/, '') || '-';

    let outputsHtml = '';
    if (r.outputs?.length) {
      outputsHtml = '<div class="task-outputs">' + r.outputs.map(o => {
        const url = esc(o.url || o.local_path || '');
        return `<img class="output-thumb" src="${url}" onclick="openLightbox('${url}')" onerror="this.style.opacity='0.3'">
          <a class="output-link" href="${url}" target="_blank">${esc(o.type || 'file')}</a>`;
      }).join('') + '</div>';
    } else {
      outputsHtml = '<div class="task-outputs"><div class="no-output">无产出</div></div>';
    }

    const errorHtml = r.error ? `<div class="error-msg">⚠ ${esc(r.error)}</div>` : '';

    let paramsHtml = '';
    if (r.extra_params && Object.keys(r.extra_params).length > 0) {
      const rows = Object.entries(r.extra_params).map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td>${esc(String(v))}</td></tr>`
      ).join('');
      paramsHtml = `<details class="extra-params"><summary>提交参数 (${Object.keys(r.extra_params).length})</summary><table>${rows}</table></details>`;
    }

    return `<div class="task-card">
      <div class="task-top">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="task-id">${esc(id)}<button class="copy-btn" onclick="copyId('${esc(id)}')">复制</button></span>
          <span class="status-badge status-${esc(r.status)}">${esc(r.status)}</span>
        </div>
        <span class="task-time">${esc(ts)}</span>
      </div>
      <div class="task-body">
        <div class="task-info">
          <div class="task-prompt">${esc(r.prompt || '(无提示词)')}</div>
          <div class="task-meta">
            <span>${esc(source)}</span>
            <span>${esc(model)}</span>
            ${r.endpoint ? `<span>${esc(r.endpoint)}</span>` : ''}
            ${r.charge_amount ? `<span>${r.charge_amount} 积分</span>` : ''}
          </div>
          ${errorHtml}
          ${paramsHtml}
        </div>
        ${outputsHtml}
      </div>
    </div>`;
  }).join('');
}

function openLightbox(url) {
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox').classList.add('open');
}

document.getElementById('filters').addEventListener('click', e => {
  if (!e.target.classList.contains('filter-btn')) return;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  FILTER = e.target.dataset.filter;
  renderTimeline(DATA, FILTER, SEARCH);
});

document.getElementById('searchInput').addEventListener('input', e => {
  SEARCH = e.target.value;
  renderTimeline(DATA, FILTER, SEARCH);
});

document.addEventListener('keydown', e => { if (e.key === 'Escape') document.getElementById('lightbox').classList.remove('open'); });

renderStats(DATA);
renderTimeline(DATA, 'all', '');
</script>
</body>
</html>
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成 BizyAir 任务日志查看页面')
    parser.add_argument('--enriched', default=ENRICHED_DEFAULT, help='enriched records JSON 路径')
    parser.add_argument('--jsonl', default=JSONL_DEFAULT, help='本地 JSONL 日志路径')
    parser.add_argument('-o', '--output', help='输出 HTML 路径')
    args = parser.parse_args()

    records = {}

    # 1. 加载 API enriched 记录（以 request_id 去重）
    if os.path.exists(args.enriched):
        with open(args.enriched, encoding='utf-8') as f:
            enriched = json.load(f)
        for r in enriched:
            rid = r.get('request_id') or r.get('task_id')
            if rid:
                records[rid] = r
        print(f"从 enriched 加载 {len(enriched)} 条记录", file=sys.stderr)

    # 2. 合并本地 JSONL（覆盖 API 数据，JSONL 更新鲜）
    if os.path.exists(args.jsonl):
        with open(args.jsonl, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = r.get('request_id') or r.get('task_id')
                if rid:
                    records[rid] = r
        print(f"从 JSONL 加载 {sum(1 for _ in open(args.jsonl))} 条记录", file=sys.stderr)

    # 3. 排序：最新在前
    def sort_key(r):
        ts = r.get('unix_ts')
        if isinstance(ts, (int, float)):
            return (1, ts)
        return (0, r.get('created_at') or '')
    sorted_records = sorted(records.values(), key=sort_key, reverse=True)

    html = HTML_TEMPLATE.replace('__RECORDS__', json.dumps(sorted_records, ensure_ascii=False))

    if args.output:
        Path(args.output).write_text(html, encoding='utf-8')
        print(f"已生成: {args.output} ({len(sorted_records)} 条记录)", file=sys.stderr)
    else:
        print(html)


if __name__ == '__main__':
    main()
