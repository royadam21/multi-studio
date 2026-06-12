# 多模态随心生成 · 服务器部署

部署时间：2026-06-12
服务器：阿里云 ECS `<YOUR_SERVER_IP>` (Ubuntu 24.04 / Python 3.12)

## 部署结构

```
/opt/multimodal-studio/         # 项目目录（Flask 服务 + 前端 + 调度器）
/opt/Scripts/Scripts/           # Agnes 脚本（依赖）
├── agnes_image_gen.py
└── agnes_video_gen.py

/etc/systemd/system/multimodal-studio.service   # systemd 守护
```

## 端口

**5050**（5000 端口被服务器上其他可疑进程占用，未清理直接换端口）

## 启动 / 停止 / 状态

```bash
systemctl start multimodal-studio.service    # 启动
systemctl stop multimodal-studio.service     # 停止
systemctl restart multimodal-studio.service  # 重启
systemctl status multimodal-studio.service   # 状态
journalctl -u multimodal-studio.service -f  # 实时日志
tail -f /opt/multimodal-studio/app.log       # 应用日志
```

## 访问方式

⚠️ 实际公网域名是部署者私有信息，**不**应硬编码到代码仓库。请将下表的 `<YOUR_PUBLIC_DOMAIN>` 替换为你的实际域名（或 IP）。

| URL | 用途 |
|------|------|
| `https://<YOUR_PUBLIC_DOMAIN>` | 公网 HTTPS（推荐 certbot Let's Encrypt，90 天自动续） |
| `http://<YOUR_PUBLIC_DOMAIN>` | 自动 301 跳 HTTPS |

⚠️ 不再需要 5050 端口暴露——Nginx 80/443 反代转发到 5050。

### 部署时间线（2026-06-12）
- 10:55 收到部署需求
- 10:58 systemd 守护 + 端口 5050（避开 5000 可疑进程）
- 11:10 Nginx 配好 + certbot HTTPS
- 11:12 全公网 HTTPS 通，Let's Encrypt 证书（90 天自动续期）

要让主人从公网访问，**任选其一**：

### 方案 A：阿里云控制台开安全组（推荐，最稳）
1. 登录 https://ecs.console.aliyun.com
2. 找到这台 ECS（`<ECS_INSTANCE_ID>`）
3. 安全组 → 入方向 → 手动添加
   - 端口：`5050/5050`
   - 协议：TCP
   - 授权对象：`0.0.0.0/0`（或主人的 IP）
4. 添加后访问：`http://<YOUR_SERVER_IP>:5050/`

### 方案 B：SSH 端口转发（临时，主人自己跑）
在主人的 Windows PowerShell 上：
```powershell
ssh -L 5050:127.0.0.1:5050 -N root@<YOUR_SERVER_IP>
```
然后浏览器访问：`http://127.0.0.1:5050/`

### 方案 C：Nginx 反向代理 + 80/443
适合长期对外 + 域名 + HTTPS（虾砌码按需配置）

## 关键环境变量（systemd service 里）

```
MMS_HOST=0.0.0.0
MMS_PORT=5050
MMS_WORKSPACE_ROOT=/opt/Scripts
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
```

## 数据库 & 任务产物路径

- 数据库：`/opt/multimodal-studio/data/tasks.db`
- 图片输出：`/opt/multimodal-studio/tasks/images/`
- 视频输出：`/opt/multimodal-studio/tasks/videos/`

## 配置改动

### config.py 跨平台化
- 改用 `MMS_HOST`/`MMS_PORT`/`MMS_WORKSPACE_ROOT`/`MMS_AGNES_KEY` 环境变量覆盖
- Linux/macOS 默认 `0.0.0.0`（生产），Windows 默认 `127.0.0.1`（本地）
- Agnes 脚本路径从固定 Windows 路径 → 探测式 + 环境变量优先

### scheduler.py / app.py
- `sys.stdout.reconfigure` 加 Windows 平台判断
- `log()` 函数：Windows ASCII 转义 / Linux 原样输出
- `_run_subprocess_windows` 保留 `sys.platform == 'win32'` 条件分支（实际已跨平台）

### agnes_image_gen.py / agnes_video_gen.py
- `sys.stdout.reconfigure` 加 Windows 平台判断
