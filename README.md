# bizyair-skill

remio agent 内部技能：通过 BizyAir API（ModelZoo + WebApp）批量提交异步图片生成任务，自动同步到 Cloudflare Worker viewer，并通过 Lsky Pro 图床代理解决 HTTPS 混合内容问题。

## 核心功能

- 🔌 **BizyAir API 集成**（ModelZoo + WebApp 两种执行路径）
- 🖼️ **自动图床化**：BizyAir CDN URL → Lsky Pro → Cloudflare Worker HTTPS 代理 URL
- 📊 **Cloudflare Worker Viewer**：实时查看任务日志、缩略图、lightbox
- 🔄 **增量同步**：本地 JSONL 任务日志 + KV 持久化
- 🛡️ **去重保护**：避免重复上传/重复 KV 写入

## 项目结构

```
bizyair-skill/
├── SKILL.md                    # remio agent 技能说明
├── config.json                 # API 凭证（请填入自己的 api_key）
├── config/                     # 静态路由/错误码/菜单配置
├── references/                 # API 端点详细文档
└── scripts/                    # Python 工具脚本
    ├── api.py                  # 底层 HTTP 调用
    ├── modelzoo.py             # ModelZoo 路径
    ├── remote.py               # WebApp 路径
    ├── search.py               # 任务查询
    ├── task_logger.py          # JSONL 任务日志读写
    ├── push_tasks.py           # 推送到 CF Worker
    ├── lsky_upload.py          # 单图上传 Lsky Pro
    ├── lsky_rereupload.py      # 批量下载→上传→替换
    └── bizyair_viewer/         # CF Worker 源码（独立 git）
```

## 快速开始

### 1. 配置

```bash
# 复制并填入你的 BizyAir API key
cp config.json.example config.json  # 或直接编辑
# 编辑 config.json，把 <YOUR_BIZYAIR_API_KEY> 替换为你的 key
```

### 2. 部署 Viewer

```bash
cd bizyair_viewer
wrangler kv namespace create TASK_KV
# 把 id 填到 wrangler.toml
wrangler deploy
```

### 3. 推任务

```bash
python3 scripts/push_tasks.py https://your-worker.workers.dev
```

## License

MIT

## Demo

部署后的 viewer 界面（开发环境样例）：

```
┌────────────────────────────────────────────────────────┐
│  BizyAir Task Viewer                  [✓ 220] [✗ 5]  │
│  Search: [_______________]  Filter: [all|done|err]   │
├────────────────────────────────────────────────────────┤
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐  6a23c755d96c0.png          │
│  │ 🟢│ │ 🟢│ │ 🟢│ │ 🟢│  请求ID: req_abc123        │
│  └───┘ └───┘ └───┘ └───┘  提示词: a beautiful...     │
│   06/06  06/06  06/06  06/06                         │
│                                                        │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐  ae451cbd...png            │
│  │ 🟡│ │ 🟢│ │ 🟢│ │ 🟢│  异步中 / 完成 / 完成 / 完成│
│  └───┘ └───┘ └───┘ └───┘                             │
└────────────────────────────────────────────────────────┘
```

每个缩略图点击进入 lightbox 大图模式。

## 架构图

```
┌─────────────┐    POST /api/tasks     ┌────────────────┐
│ Python 脚本 │ ──────────────────────▶ │ CF Worker      │
│ (push_tasks)│                         │ (viewer)        │
└─────────────┘                         └────────┬────────┘
                                                 │
                              ┌──────────────────┼──────────────────┐
                              ▼                  ▼                  ▼
                        ┌──────────┐       ┌──────────┐       ┌──────────┐
                        │ CF KV    │       │ Browser  │       │ Upstream │
                        │ (TASK_KV)│       │ 加载 /   │       │ Lsky     │
                        │          │       │ /proxy   │       │ (HTTP)   │
                        └──────────┘       └────┬─────┘       └────┬─────┘
                                                 │                  ▲
                                                 └──── fetch() ─────┘
                                                     (CF 边缘缓存 30 天)
```
