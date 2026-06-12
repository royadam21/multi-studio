# 多模态随心生成 · Spec 文档

> 项目代号：multimodal-studio
> 创建日期：2026-06-12
> 主人：虾砌码 🦞
> 版本：v1.0

---

## 1. 项目目标

把 `Scripts/agnes_image_gen.py` 和 `Scripts/agnes_video_gen.py` 两个 CLI 脚本升级为**可视化 Web 任务工作台**，让主人通过浏览器：

- 📋 **看任务列表**：所有已提交的生成任务一览无余
- ➕ **新建任务**：表单填好提示词 + 参数一键提交
- 🔄 **实时状态**：任务状态（排队/运行/成功/失败）自动刷新
- 🖼️ **结果预览**：图片/视频直接在页面里看
- 📋 **复制提示词**：方便复用和微调

## 2. 技术栈

| 层 | 技术 | 理由 |
|----|------|------|
| 后端 | **Python 3.11 + Flask 3.x** | 主人熟悉，集团考核/抱石日历/财报分析都用 Flask |
| 前端 | **单 HTML + Bootstrap 5.3 + 原生 JS** | 千面 skill 兼容；零构建；双击 HTML 可看 |
| 数据库 | **SQLite 3** | 零部署；单文件；任务列表场景够用 |
| 任务调度 | **Python threading.Thread + 定时轮询** | 简单可控；图片跑 15-30s 串行足够；视频异步 task_id 轮询 |
| 外部 API | **Agnes Image/Video API** | 复用现有 `Scripts/agnes_*.py`（subprocess 调用） |
| 设计 | **千面 design system (Dark OLED + IBM Plex)** | 工业克制 + 暗色护眼 |

## 3. 项目结构

```
projects/multimodal-studio/
├── app.py                  # Flask 主入口（路由 + API）
├── scheduler.py            # 任务调度（subprocess + 轮询）
├── db.py                   # SQLite 封装（CRUD）
├── config.py               # 配置常量
├── requirements.txt
├── README.md
├── data/
│   └── tasks.db            # SQLite 数据库
├── tasks/                  # 任务输出目录
│   ├── images/
│   └── videos/
├── templates/
│   └── index.html          # 主页面
├── static/
│   ├── css/style.css       # 自定义样式（千面设计 token）
│   └── js/app.js           # 前端逻辑
├── docs/
│   └── SPEC.md             # 本文档
└── tests/
    └── test_smoke.py       # 冒烟测试
```

## 4. 数据模型

### 4.1 `tasks` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PRIMARY KEY | 任务 ID（`img_<时间戳毫秒>_<4位随机>` 或 `vid_<...>`） |
| `name` | TEXT NOT NULL | 任务名（用户填的） |
| `type` | TEXT NOT NULL | `image` / `video` |
| `model` | TEXT NOT NULL | `agnes-image-2.1-flash` / `agnes-video-v2.0` |
| `prompt` | TEXT NOT NULL | 提示词 |
| `params` | TEXT (JSON) | 其他参数（size/width/height/num_frames 等） |
| `status` | TEXT NOT NULL | `pending` / `running` / `success` / `failed` |
| `remote_task_id` | TEXT | Agnes 返回的 task_id（视频异步用） |
| `result_path` | TEXT | 生成的本地文件路径（相对项目根） |
| `result_url` | TEXT | Agnes 远程 URL（图片用） |
| `error_msg` | TEXT | 失败信息 |
| `created_at` | INTEGER | 创建时间（Unix ms） |
| `started_at` | INTEGER | 开始执行时间 |
| `finished_at` | INTEGER | 完成时间 |

### 4.2 索引

- `idx_status` ON `status`（过滤待执行/运行中的任务）
- `idx_type_created` ON `type, created_at DESC`（按类型+最新优先）

## 5. API 设计（RESTful）

### 5.1 任务相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks?type=image&status=running&limit=50` | 任务列表（支持按 type/status 过滤） |
| GET | `/api/tasks/<id>` | 任务详情 |
| POST | `/api/tasks` | 创建任务 |
| POST | `/api/tasks/<id>/retry` | 重试失败任务 |
| DELETE | `/api/tasks/<id>` | 删除任务（同时删文件） |
| GET | `/api/tasks/<id>/result` | 结果文件（图片/视频） |

### 5.2 系统相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面（index.html） |
| GET | `/api/models?type=image` | 可用模型列表 |
| GET | `/api/health` | 健康检查 |

### 5.3 POST 任务请求体

```json
{
  "name": "古典美人烛下读卷",
  "type": "image",
  "model": "agnes-image-2.1-flash",
  "prompt": "A beautiful Chinese woman...",
  "params": {
    "size": "1024x1280",
    "count": 1
  }
}
```

视频任务 params 字段：
```json
{
  "width": 1152,
  "height": 768,
  "num_frames": 121,
  "frame_rate": 24,
  "negative_prompt": ""
}
```

### 5.4 任务列表响应

```json
{
  "code": 0,
  "data": {
    "tasks": [
      {
        "id": "img_1718173456789_a1b2",
        "name": "古典美人烛下读卷",
        "type": "image",
        "model": "agnes-image-2.1-flash",
        "status": "success",
        "prompt": "...",
        "result_path": "tasks/images/xxx.png",
        "created_at": 1718173456789,
        "finished_at": 1718173480123,
        "duration_ms": 25334
      }
    ],
    "total": 42
  }
}
```

## 6. 前端页面

### 6.1 布局

```
┌──────────────────────────────────────────────────────────┐
│ Header: 多模态随心生成         [图片 3] [视频 1]  [+ 新建] │
├──────────────────────────────────────────────────────────┤
│ Tabs: [图片生成] [视频生成]                                │
├──────────────────────────────────────────────────────────┤
│ Task Table:                                                │
│ ID | 任务名 | 模型 | 状态 | 创建时间 | 完成时间 | 操作      │
│ ...                                                        │
└──────────────────────────────────────────────────────────┘

点击 [+ 新建] → 右侧滑出抽屉（480px 宽）
┌─────────────────┐
│ 新建任务 ✕     │
├─────────────────┤
│ 任务名:        │
│ [_________]    │
│                │
│ 类型: ◉图片 ○视频│
│                │
│ 模型:          │
│ [下拉框]       │
│                │
│ 提示词:        │
│ [textarea]     │
│                │
│ 参数:          │
│ 尺寸: [1024x1280]│
│ 数量: [1]     │
│                │
│ [取消] [提交] │
└─────────────────┘
```

### 6.2 交互细节

- **状态实时刷新**：每 3 秒轮询一次（只查 running 状态的任务）
- **状态徽章**：
  - `pending`：灰 + 时钟图标
  - `running`：蓝 + spinner 旋转
  - `success`：绿 + check 图标
  - `failed`：红 + x 图标
- **操作按钮**：详情 / 复制提示词 / 预览 / 重试 / 删除
- **结果预览**：图片直接显示；视频 `<video controls>`

### 6.3 设计 token（千面规范）

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg-primary` | `#0A0A0F` | 页面底色（OLED 黑） |
| `--bg-card` | `#13131A` | 卡片底色 |
| `--bg-elevated` | `#1C1C26` | 弹窗/抽屉 |
| `--border` | `#2A2A38` | 边框 |
| `--text-primary` | `#F4F4F5` | 主文字 |
| `--text-secondary` | `#A1A1AA` | 次文字 |
| `--text-muted` | `#71717A` | 弱化文字 |
| `--accent` | `#6366F1` | 靛蓝主色 |
| `--accent-hover` | `#818CF8` | 悬停态 |
| `--success` | `#10B981` | 成功 |
| `--warning` | `#F59E0B` | 警告/活跃 |
| `--danger` | `#EF4444` | 失败/删除 |
| `--info` | `#3B82F6` | 运行中 |
| `--font-sans` | `IBM Plex Sans, PingFang SC, Microsoft YaHei, sans-serif` |
| `--font-mono` | `JetBrains Mono, Menlo, Consolas, monospace` |
| `--radius-sm` | `6px` | 按钮、输入框 |
| `--radius-md` | `12px` | 卡片 |
| `--radius-lg` | `20px` | 抽屉/弹窗 |
| `--space-1` | `4px` | 间距系统基础 |

## 7. 任务调度设计

### 7.1 调度流程

```
用户提交 POST /api/tasks
  ↓
写入 DB（status=pending）
  ↓
scheduler 扫描 pending 任务
  ↓
标记 running + 启动子进程（subprocess.Popen）
  ↓
【图片任务】阻塞到进程结束，解析 exit code
   - 0: 从 .agnes_cache/ 读 url → 下载到 tasks/images/ → success
   - ≠0: 读 stderr → failed
  ↓
【视频任务】非阻塞，保存 task_id 到 DB
   - 后台轮询线程每 30s 查一次任务状态
   - completed: 下载视频到 tasks/videos/ → success
   - failed: failed
  ↓
更新 DB（status=success/failed）
```

### 7.2 调度实现

- **Flask 启动时**：创建 `Scheduler` 单例
- **后台线程 A**：每 3 秒扫描 `pending` 任务 → 启动子进程
- **后台线程 B**：每 30 秒扫描 `running` 视频任务 → 查 Agnes API
- **最大并发**：图片 3 个并发（串行队列），视频 1 个并发（Agnes 限流）

### 7.3 错误处理

| 场景 | 处理 |
|------|------|
| API key 失效 | 任务标记 failed，error_msg 写明 |
| 提示词 NSFW | Agnes 拒绝，任务 failed，error_msg 含原始响应 |
| 网络超时 | subprocess 超时 10 分钟，标记 failed |
| 子进程崩溃 | exit code ≠ 0，stderr 写入 error_msg |
| 磁盘满 | 下载异常 → failed + 提示 |

## 8. 配置

### 8.1 `config.py`

```python
# 服务
HOST = '127.0.0.1'
PORT = 5000
DEBUG = False

# 数据库
DB_PATH = 'data/tasks.db'

# 任务输出
TASKS_DIR = 'tasks'
IMAGES_DIR = 'tasks/images'
VIDEOS_DIR = 'tasks/videos'

# 调度
POLL_INTERVAL = 3            # 任务列表刷新频率
VIDEO_POLL_INTERVAL = 30     # 视频任务轮询频率
MAX_IMAGE_CONCURRENCY = 3    # 图片最大并发
MAX_VIDEO_CONCURRENCY = 1    # 视频最大并发
SUBPROCESS_TIMEOUT = 600     # 子进程超时（秒）

# Agnes API（复用 Scripts 中的常量）
AGNES_API_KEY = os.environ.get('MMS_AGNES_KEY', '<YOUR_AGNES_API_KEY>')  # 环境变量覆盖；不要硬编码
AGNES_BASE_URL = 'https://apihub.agnes-ai.com/v1'

# Agnes 脚本路径
AGNES_IMAGE_SCRIPT = 'C:/Users/11985/.qclaw/workspace-codingclaw/Scripts/agnes_image_gen.py'
AGNES_VIDEO_SCRIPT = 'C:/Users/11985/.qclaw/workspace-codingclaw/Scripts/agnes_video_gen.py'
```

## 9. 部署

### 9.1 本地运行

```bash
cd projects/multimodal-studio
pip install -r requirements.txt
py -3 app.py
# 访问 http://127.0.0.1:5000
```

### 9.2 阿里云部署（可选）

```bash
# 用 scp 推到服务器
scp -r projects/multimodal-studio root@<YOUR_SERVER_IP>:/opt/

# 服务器启动
ssh root@<YOUR_SERVER_IP>
cd /opt/multimodal-studio
pip install -r requirements.txt
nohup py -3 app.py > app.log 2>&1 &
```

## 10. 测试计划

### 10.1 冒烟测试（v1 必过）

- [ ] Flask 启动无报错
- [ ] GET /api/health 返回 200
- [ ] GET /api/tasks 返回空列表
- [ ] GET / 渲染 index.html
- [ ] 提交 1 个图片任务 → 状态从 pending → running → success
- [ ] 提交 1 个视频任务 → 状态从 pending → running → success（轮询）

### 10.2 边界测试（v2 完善）

- [ ] 提交 NSFW 提示词 → 任务 failed，error_msg 友好
- [ ] 重复提交同 prompt → 第二次命中缓存（30 秒内）
- [ ] 删除任务 → 文件 + DB 记录都删
- [ ] 重试失败任务 → 重新跑

## 11. 后续迭代（v2+）

- [ ] 任务标签/分组
- [ ] 提示词模板库（保存常用 prompt）
- [ ] 导出任务列表为 CSV
- [ ] WebSocket 实时推送（替代轮询）
- [ ] 用户登录/多用户
- [ ] 阿里云部署 + 域名
- [ ] MiniMax / 百炼等其他模型接入

---

## 12. 风险 & 决策记录

| 决策 | 原因 |
|------|------|
| 不用 Vue/React | 主人项目一贯轻量（抱石日历/财报分析都是原生 HTML） |
| 不用 WebSocket | 轮询 3 秒足够，状态变化不频繁 |
| 复用现有脚本 | 不重写逻辑，subprocess 调用降低维护成本 |
| 千面 Dark OLED | 主人主用户在晚间；紫粉配色太"AI 味"改成靛蓝+琥珀 |
| 任务输出存本地 | 阿里云部署再考虑对象存储 |

---

*虾砌码 🦞 2026-06-12*
