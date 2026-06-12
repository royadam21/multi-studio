# 🎨 Multimodal Studio

> **一站式多模态生成 Web 应用** · 文本/图片/视频生成 · 异步任务调度 · 实时进度推送

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Multimodal Studio** 是一个轻量级 Web 工具，集成 **Agnes AI** 平台的多种生成能力（图像 / 视频 / 提示词生成），通过统一的任务调度器和友好的前端界面，让创作者可以并行管理多种生成任务。

---

## ✨ 核心特性

### 1. **三种任务类型**
| Tab | 模型 | 输出 | 典型耗时 |
|-----|------|------|----------|
| **🖼️ 图片生成** | agnes-image-2.1-flash | PNG | 15-30s |
| **🎬 视频生成** | agnes-video-v2.0 | MP4 (5s, 24fps) | 5-10min |
| **💡 提示词生成** | agnes-2.0-flash | 文本 | 3-10s |

### 2. **异步任务调度**
- ✅ 基于 SQLite + threading 实现的轻量调度器
- ✅ 并发控制（图片 3 并发 / 视频 1 并发）
- ✅ 失败任务支持 **重试**（保留参数 + 复用远程 task_id）
- ✅ 状态轮询 + 实时前端进度

### 3. **友好前端**
- ✅ Bootstrap 5 + 原生 HTML/CSS/JS（无构建工具）
- ✅ Tab 切换、抽屉式新建、Toast 通知
- ✅ 一键复制结果、批量管理

### 4. **多模态输入**
- ✅ 文本提示词
- ✅ 参考图（图生图 / 图生视频）
- ✅ 多图视频、关键帧动画（视频模型支持）

---

## 📦 架构

```
┌─────────────────────────────────────────────────────────┐
│                  Browser (HTML + JS)                    │
│  ┌────────┐ ┌────────┐ ┌────────┐                      │
│  │ 图片tab│ │ 视频tab│ │ 提示词 │  ← 统一任务列表        │
│  └────┬───┘ └────┬───┘ └────┬───┘                      │
└───────┼──────────┼──────────┼──────────────────────────┘
        │    fetch /api/tasks /api/tasks/<id> /api/tasks (POST)
┌───────▼──────────▼──────────▼──────────────────────────┐
│                Flask app.py (5050)                       │
│  - /api/tasks           (POST 创建 / GET 列表)            │
│  - /api/tasks/<id>      (GET 详情 / DELETE 联动)         │
│  - /api/tasks/<id>/retry                                │
│  - /api/models          (按类型返回可用模型)              │
│  - /refs/<filename>     (图床代理)                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│         scheduler.py (后台线程调度器)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ image worker │  │ video worker │  │ text worker  │   │
│  │  (并发=3)    │  │  (并发=1)    │  │  (并发=待定)  │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         └─────────────────┼─────────────────┘           │
└───────────────────────────┼─────────────────────────────┘
                            │ subprocess.run
┌───────────────────────────▼─────────────────────────────┐
│  /opt/Scripts/Scripts/  (外部依赖)                        │
│   ├─ agnes_image_gen.py    (图片生成)                     │
│   ├─ agnes_video_gen.py    (视频生成)                     │
│   └─ agnes_prompt_gen.py   (提示词生成)                   │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS (Bearer)
┌───────────────────────────▼─────────────────────────────┐
│             Agnes AI (apihub.agnes-ai.com)                │
│   POST /v1/images/generations  |  POST /v1/videos        │
│   POST /v1/chat/completions    |  GET  /v1/models        │
└───────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 环境要求
- **Python 3.11+**
- **操作系统**：Windows 10+ / macOS / Linux（推荐 Ubuntu 22.04+）
- **依赖**：`flask`, `requests`（见 `requirements.txt`）

### 2. 安装

```bash
# 克隆仓库
git clone https://github.com/royadam21/multi-studio.git
cd multi-studio

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量（⚠️ 不要硬编码 API Key）

在项目根目录创建 `.env` 文件（**不会**进 Git）：

```bash
# .env
MMS_AGNES_KEY=sk-your-agnes-api-key-here
MMS_BASE_URL=https://apihub.agnes-ai.com/v1
MMS_HOST=127.0.0.1
MMS_PORT=5050
MMS_WORKSPACE_ROOT=/path/to/your/Scripts   # agnes_*.py 所在目录
```

> **Windows** 推荐用 PowerShell `$env:MMS_AGNES_KEY = "sk-..."`
> **Linux/macOS** 推荐 systemd Environment 或 `.env` + python-dotenv

### 4. 准备外部依赖脚本

本项目**不包含** Agnes 脚本（`agnes_image_gen.py` / `agnes_video_gen.py` / `agnes_prompt_gen.py`），它们位于 `$MMS_WORKSPACE_ROOT/Scripts/` 目录。

详见姊妹项目 [`agn-studio-scripts`](https://github.com/royadam21/agn-studio-scripts)（如果你 fork 了）或个人本地仓库。

### 5. 启动

```bash
# 开发模式
python app.py

# 生产模式（推荐 systemd，详见 docs/DEPLOY.md）
nohup python app.py > app.log 2>&1 &
```

浏览器访问 `http://127.0.0.1:5050/`

---

## 📂 项目结构

```
multimodal-studio/
├── app.py                    # Flask 应用 + 路由 + 静态文件
├── scheduler.py              # 后台调度器（线程 + 轮询 + 并发控制）
├── config.py                 # 配置（环境变量 + 默认值）
├── db.py                     # SQLite 封装（任务 CRUD）
├── requirements.txt
├── .gitignore
├── README.md
├── docs/
│   ├── SPEC.md               # 详细设计规格
│   └── DEPLOY.md             # 服务器部署指南（systemd + Nginx + HTTPS）
├── templates/
│   └── index.html            # 单页应用模板
├── static/
│   ├── css/style.css         # 主样式
│   └── js/app.js             # 前端逻辑
├── data/                     # SQLite 数据库（gitignore）
├── tasks/                    # 任务产物（gitignore）
│   ├── images/               # 生成的图片
│   ├── videos/               # 生成的视频
│   ├── texts/                # 生成的提示词
│   └── .agnes_cache/         # 幂等缓存
└── tests/                    # 单元测试
```

---

## ⚙️ 配置项

所有配置走 `config.py` + 环境变量覆盖。**生产环境务必用环境变量**。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MMS_AGNES_KEY` | `<YOUR_AGNES_API_KEY>` | **必填**，Agnes API Key |
| `MMS_BASE_URL` | `https://apihub.agnes-ai.com/v1` | Agnes API 根 |
| `MMS_HOST` | `0.0.0.0`（Linux）/ `127.0.0.1`（Win） | Flask 监听地址 |
| `MMS_PORT` | `5050` | Flask 端口 |
| `MMS_WORKSPACE_ROOT` | 自动探测 | 外部 Scripts 目录的父级 |
| `MMS_AGNES_IMAGE_SCRIPT` | 自动 | 图片脚本路径（可显式覆盖） |
| `MMS_AGNES_VIDEO_SCRIPT` | 自动 | 视频脚本路径 |
| `MMS_AGNES_TEXT_SCRIPT` | 自动 | 提示词脚本路径 |
| `MMS_MAX_IMAGE_CONCURRENCY` | `3` | 图片最大并发 |
| `MMS_MAX_VIDEO_CONCURRENCY` | `1` | 视频最大并发 |
| `MMS_POLL_INTERVAL` | `3` | 任务列表轮询间隔（秒） |
| `MMS_VIDEO_POLL_INTERVAL` | `30` | 视频状态轮询间隔（秒） |
| `MMS_SUBPROCESS_TIMEOUT` | `600` | 子进程超时（秒） |

---

## 🔌 API 文档

### `POST /api/tasks`
创建新任务。

**请求体**：
```json
{
  "name": "我的图片",
  "type": "image",          // image | video | text
  "model": "agnes-image-2.1-flash",
  "prompt": "...",
  "input_text": "...",        // text 类型必填
  "input_image": "https://...", // 可选
  "params": {
    "width": 1152,
    "height": 768,
    "num_frames": 121,
    "frame_rate": 24,
    "temperature": 0.7,
    "max_tokens": 1024
  }
}
```

**响应**：
```json
{
  "code": 0,
  "data": {
    "task_id": "img_1781239757037_ol43"
  }
}
```

### `GET /api/tasks?type=image&limit=200`
获取任务列表。

### `GET /api/tasks/<task_id>`
获取单个任务详情（含 result_path / result_text / result_url）。

### `DELETE /api/tasks/<task_id>`
删除任务（**联动删除** `tasks/images/*.png` 和 `tasks/videos/*.mp4`；**不**删除 `tasks/.agnes_cache/` 跨任务共享缓存）。

### `POST /api/tasks/<task_id>/retry`
重试失败任务（保留参数 + 复用 agnes 远程 task_id 做幂等）。

### `GET /api/models?type=image`
返回指定类型可用模型列表。

---

## 🧪 测试

```bash
# 单元测试
python -m pytest tests/

# 烟雾测试（需先启动 app）
python tests/smoke_test.py
```

---

## 🚢 部署

### 本地开发
直接 `python app.py` 即可。

### 生产环境（systemd + Nginx + HTTPS）

详见 [`docs/DEPLOY.md`](docs/DEPLOY.md)：
- systemd 服务管理
- Nginx 反向代理
- Let's Encrypt HTTPS 证书
- 多用户并发配置

### Docker（TODO）
暂未提供 Dockerfile，欢迎 PR。

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Bootstrap 5 + 原生 HTML/CSS/JS（无 React/Vue） |
| 后端 | Flask 3.x（单进程 + threading） |
| 调度 | Python threading + SQLite + subprocess |
| 存储 | SQLite（WAL 模式）+ 本地文件系统 |
| 部署 | systemd + Nginx + Let's Encrypt |
| 外部 API | Agnes AI（OpenAI 兼容协议） |

---

## 🐛 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| 任务一直 pending | 调度器没起 / 并发占满 | 看 `app.log` + `systemctl status` |
| 视频生成 SSH 异常 | 旧版 agnes_video_gen.py 走 SSH 中转 | 升级到直连 API 版本（v4+） |
| 500 Internal Server Error | DB schema 不匹配 | 删 `data/tasks.db` 重建 |
| 提示词生成空白 | input_text 字段没传 | 前端检查 / 手动 SQL 验证 |
| 前端 tab 角标 0 | 浏览器缓存旧版 app.js | Ctrl+Shift+R 强刷 |

---

## 📜 更新日志

### v1.0 (2026-06-12)
- ✨ 三种任务类型：image / video / text
- ✨ 异步调度器（并发控制 + 轮询 + 重试）
- ✨ 前端：Tab + 抽屉 + Toast
- ✨ 部署：systemd + Nginx + HTTPS
- ✨ 文档：完整 SPEC + DEPLOY + README

---

## 🤝 贡献

欢迎 PR！建议方向：
- [ ] Dockerfile 容器化
- [ ] pytest 单元测试覆盖
- [ ] WebSocket 实时进度推送（替代轮询）
- [ ] 多用户权限管理
- [ ] 历史任务归档 + 清理脚本
- [ ] 任务队列可视化（Web UI）

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

## 🙏 致谢

- [Agnes AI](https://agnes-ai.com) - 多模态生成 API
- [Flask](https://flask.palletsprojects.com) - Web 框架
- [Bootstrap](https://getbootstrap.com) - UI 组件

---

**维护者**：[royadam21](https://github.com/royadam21)
**最后更新**：2026-06-12
