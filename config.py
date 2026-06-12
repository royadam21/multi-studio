# -*- coding: utf-8 -*-
"""多模态随心生成 · 配置

环境变量覆盖（部署服务器用）：
- MMS_HOST             默认 0.0.0.0（生产）/ 127.0.0.1（本地）
- MMS_PORT             默认 5000
- MMS_WORKSPACE_ROOT   Agnes 脚本所在目录（默认 = 本项目父目录/Scripts）
- MMS_AGNES_KEY        Agnes API Key
- MMS_BASE_URL         Agnes API 根
"""
import os
from pathlib import Path

# ============== 服务 ==============
def _resolve_host() -> str:
    env = os.environ.get('MMS_HOST')
    if env:
        return env
    # Linux/macOS = 服务器，默认 0.0.0.0；Windows = 本地开发，默认 127.0.0.1
    return '0.0.0.0' if os.name != 'nt' else '127.0.0.1'

HOST = _resolve_host()
PORT = int(os.environ.get('MMS_PORT', '5000'))
DEBUG = os.environ.get('MMS_DEBUG', '0') == '1'

# ============== 项目根 ==============
PROJECT_ROOT = Path(__file__).parent.resolve()

# ============== 数据库 ==============
DB_PATH = PROJECT_ROOT / 'data' / 'tasks.db'

# ============== 任务输出 ==============
TASKS_DIR = PROJECT_ROOT / 'tasks'
IMAGES_DIR = TASKS_DIR / 'images'
VIDEOS_DIR = TASKS_DIR / 'videos'

# ============== Workspace 根（Agnes 脚本所在目录）==============
def _resolve_workspace_root() -> Path:
    env = os.environ.get('MMS_WORKSPACE_ROOT')
    if env:
        return Path(env)
    # 默认推断：项目根的兄弟目录里找 Scripts/
    # 部署结构: /opt/multimodal-studio/ + /opt/Scripts/
    candidate = PROJECT_ROOT.parent / 'Scripts'
    if candidate.exists():
        return candidate.parent
    # 本地开发：C:\Users\11985\.qclaw\workspace-codingclaw\projects\multimodal-studio\
    # WORKSPACE = C:\Users\11985\.qclaw\workspace-codingclaw
    return PROJECT_ROOT.parent  # 兜底

WORKSPACE_ROOT = _resolve_workspace_root()

# ============== 调度 ==============
POLL_INTERVAL = 3                # 任务状态刷新频率（前端轮询）
SCHEDULER_TICK = 1               # 后台扫描 pending 任务间隔（秒）
VIDEO_POLL_INTERVAL = 30         # 视频任务 Agnes API 轮询间隔（秒）
MAX_IMAGE_CONCURRENCY = 3        # 图片最大并发
MAX_VIDEO_CONCURRENCY = 3        # 视频最大并发（v5 submit 模式秒级返回，可多提交）
# 视频模型生成 5-10 分钟，agnes_video_gen.py --max-wait 默认 900s
# scheduler 必须 >= 900 + 启动+下载余量 = 1200
# 图片/提示词 不需要 10 分钟，但仍用 600 走默认
SUBPROCESS_TIMEOUT = 1200        # 子进程超时（秒）

# ============== Agnes API ==============
AGNES_API_KEY = os.environ.get('MMS_AGNES_KEY', '<YOUR_AGNES_API_KEY>')  # ⚠️ GitHub 上必须用环境变量，覆盖默认值
AGNES_BASE_URL = os.environ.get('MMS_BASE_URL', 'https://apihub.agnes-ai.com/v1')

# ============== Agnes 脚本路径 ==============
# 优先环境变量 / 部署目录，否则从 WORKSPACE_ROOT/Scripts/ 取
def _resolve_agnes_script(name: str) -> Path:
    env = os.environ.get(f'MMS_{name.upper()}_SCRIPT')
    if env:
        return Path(env)
    return WORKSPACE_ROOT / 'Scripts' / f'{name}.py'

AGNES_IMAGE_SCRIPT = _resolve_agnes_script('agnes_image_gen')
AGNES_VIDEO_SCRIPT = _resolve_agnes_script('agnes_video_gen')
AGNES_TEXT_SCRIPT = _resolve_agnes_script('agnes_prompt_gen')

# ============== 可用模型 ==============
AVAILABLE_MODELS = {
    'image': [
        {'id': 'agnes-image-2.1-flash', 'name': 'Agnes Image 2.1 Flash（推荐）', 'default': True},
        {'id': 'agnes-image-2.0-flash', 'name': 'Agnes Image 2.0 Flash（旧版）', 'default': False},
    ],
    'video': [
        {'id': 'agnes-video-v2.0', 'name': 'Agnes Video V2.0（电影级）', 'default': True},
    ],
    'text': [
        # 文本模型不在图片/视频默认流中；不设 default，前端不自动选
        {'id': 'agnes-2.0-flash', 'name': 'Agnes 2.0 Flash（多模态文本）', 'default': True},
    ],
}

# ============== 图片默认参数 ==============
DEFAULT_IMAGE_SIZE = '1024x1024'
DEFAULT_IMAGE_COUNT = 1
MAX_IMAGE_COUNT = 5
SUPPORTED_IMAGE_SIZES = [
    '1024x1024', '1024x1280', '1280x1024',
    '1024x768', '768x1024', '1536x1024', '1024x1536',
    '2048x2048', '512x512',
]

# ============== 视频默认参数 ==============
DEFAULT_VIDEO_WIDTH = 1152
DEFAULT_VIDEO_HEIGHT = 768
DEFAULT_VIDEO_NUM_FRAMES = 121
DEFAULT_VIDEO_FRAME_RATE = 24

# ============== 文本/提示词生成默认参数 ==============
DEFAULT_TEXT_MODEL = 'agnes-2.0-flash'
DEFAULT_TEXT_TEMPERATURE = 0.7
DEFAULT_TEXT_MAX_TOKENS = 1024
DEFAULT_TEXT_SYSTEM_PROMPT = (
    '你是一名顶级的多模态提示词工程师。'
    '根据用户给定的需求和（可选的）参考图片，生成 3-5 条针对图生成/视频生成优化的高质量提示词。'
    '要求：'
    '1) 每条提示词要具体、生动、富有画面感，适合 Stable Diffusion / Agnes / Sora 等模型；'
    '2) 直接输出提示词文本，每行一条；不要使用编号或项目符号；'
    '3) 中文输出；'
    '4) 提示词要包含：主体描述 + 场景/环境 + 风格 + 镜头/构图 + 光线 + 细节修饰。'
)
# 提示词生成任务的输出目录（文本 .txt 文件落地）
TEXTS_DIR = TASKS_DIR / 'texts'

# ============== 任务状态 ==============
STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_SUCCESS = 'success'
STATUS_FAILED = 'failed'
