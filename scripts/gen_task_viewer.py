#!/usr/bin/env python3
"""生成 BizyAir 任务日志查看页面（单文件 HTML）。

用法:
  python3 scripts/gen_task_viewer.py > /path/to/viewer.html
  python3 scripts/gen_task_viewer.py --output /path/to/viewer.html
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import task_logger

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
  .task-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 20px; margin-bottom: 10px; transition: border-color .15s;
  }
  .task-card:hover { border-color: #404040; }
  .task-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
  .task-id { font-family: "SF Mono", "Fira Code", monospace; font-size: 13px; color: var(--accent); }
  .task-time { font-size: 12px; color: var(--muted); }

  .status-badge {
    display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px;
    border-radius: 6px; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .status-Success { background: rgba(34,197,94,.15); color: var(--success); }
  .status-Failed { background: rgba(239,68,68,.15); color: var(--failed); }
  .status-AsyncSubmitted { background: rgba(245,158,11,.15); color: var(--pending); }
  .status-NoOutputs { background: rgba(239,68,68,.1); color: #f87171; }

  .task-body { display: flex; gap: 20px; align-items: flex-start; }
  .task-info { flex: 1; min-width: 0; }
  .task-prompt { font-size: 14px; line-height: 1.5; margin-bottom: 6px; word-break: break-word; }
  .task-meta { font-size: 12px; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; }
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

  .no-output { width: 80px; height: 80px; border-radius: 8px; border: 1px dashed var(--border); display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 11px; }

  .copy-btn { background: none; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 3px 8px; font-size: 11px; cursor: pointer; margin-left: 6px; }
  .copy-btn:hover { border-color: var(--accent); color: var(--text); }
</style>
</head>
<body>

<div class="header">
  <h1>📊 BizyAir 任务日志</h1>
  <div class="subtitle" id="subtitle"></div>
  <div class="stats" id="stats"></div>
</div>

<div class="filters" id="filters">
  <button class="filter-btn active" data-filter="all">全部</button>
  <button class="filter-btn" data-filter="Success">✅ 成功</button>
  <button class="filter-btn" data-filter="Failed">❌ 失败</button>
  <button class="filter-btn" data-filter="AsyncSubmitted">⏳ 异步中</button>
</div>

<div class="timeline" id="timeline"></div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('open')">
  <img id="lightbox-img" src="">
</div>

<script>
const DATA = __RECORDS__;

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function renderStats(records) {
  const total = records.length;
  const success = records.filter(r => r.status === 'Success').length;
  const failed = records.filter(r => r.status === 'Failed').length;
  const outputs = records.reduce((s, r) => s + (r.outputs?.length || 0), 0);
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="num">${total}</div><div class="label">总任务</div></div>
    <div class="stat"><div class="num" style="color:var(--success)">${success}</div><div class="label">成功</div></div>
    <div class="stat"><div class="num" style="color:var(--failed)">${failed}</div><div class="label">失败</div></div>
    <div class="stat"><div class="num">${outputs}</div><div class="label">产出文件</div></div>
  `;
}

function copyId(text) {
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = '已复制';
    setTimeout(() => btn.textContent = '复制', 1000);
  });
}

function renderTimeline(records, filter) {
  const filtered = filter === 'all' ? records : records.filter(r => r.status === filter);
  const el = document.getElementById('timeline');
  if (!filtered.length) { el.innerHTML = '<div class="empty">暂无任务记录</div>'; return; }

  el.innerHTML = filtered.map(r => {
    const id = r.request_id || r.task_id || '-';
    const model = r.model || r.app_id || '-';
    const source = r.source === 'modelzoo' ? '🔧 ModelZoo' : '🌐 WebApp';
    const ts = r.timestamp ? r.timestamp.replace('T', ' ').replace(/\+\d+$/, '') : '-';

    let outputsHtml = '';
    if (r.outputs?.length) {
      outputsHtml = '<div class="task-outputs">' + r.outputs.map(o => `
        <img class="output-thumb" src="${esc(o.url)}" onclick="openLightbox('${esc(o.url)}')" onerror="this.outerHTML='<div class=\\'no-output\\'>加载失败</div>'">
        <a class="output-link" href="${esc(o.url)}" target="_blank" title="${esc(o.url)}">${esc(o.type)}</a>
      `).join('') + '</div>';
    } else {
      outputsHtml = '<div class="task-outputs"><div class="no-output">无产出</div></div>';
    }

    const errorHtml = r.error ? `<div class="error-msg">⚠ ${esc(r.error)}</div>` : '';

    let paramsHtml = '';
    if (r.extra_params && Object.keys(r.extra_params).length > 0) {
      const rows = Object.entries(r.extra_params).map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td>${esc(String(v))}</td></tr>`
      ).join('');
      paramsHtml = `<details class="extra-params"><summary>📋 提交参数 (${Object.keys(r.extra_params).length})</summary><table>${rows}</table></details>`;
    }

    return `<div class="task-card">
      <div class="task-top">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="task-id">${esc(id)}<button class="copy-btn" onclick="copyId('${esc(id)}')">复制</button></span>
          <span class="status-badge status-${r.status}">${esc(r.status)}</span>
        </div>
        <span class="task-time">${esc(ts)}</span>
      </div>
      <div class="task-body">
        <div class="task-info">
          <div class="task-prompt">${esc(r.prompt || '(无提示词)')}</div>
          <div class="task-meta">
            <span>${source}</span>
            <span>模型: ${esc(model)}</span>
            ${r.endpoint ? `<span>${esc(r.endpoint)}</span>` : ''}
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
  renderTimeline(DATA, e.target.dataset.filter);
});

const logPath = '__LOG_PATH__';
document.getElementById('subtitle').textContent = `日志文件: ${logPath}`;

renderStats(DATA);
renderTimeline(DATA, 'all');
</script>
</body>
</html>
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成 BizyAir 任务日志查看页面')
    parser.add_argument('-o', '--output', help='输出文件路径（默认 stdout）')
    parser.add_argument('--limit', type=int, default=500, help='最多读取 N 条记录')
    args = parser.parse_args()

    records = task_logger.read_task_log(limit=args.limit)
    log_path = str(task_logger._log_file_path())

    html = HTML_TEMPLATE.replace('__RECORDS__', json.dumps(records, ensure_ascii=False))
    html = html.replace('__LOG_PATH__', log_path)

    if args.output:
        Path(args.output).write_text(html, encoding='utf-8')
        print(f'已生成: {args.output} ({len(records)} 条记录)', file=sys.stderr)
    else:
        print(html)


if __name__ == '__main__':
    main()
