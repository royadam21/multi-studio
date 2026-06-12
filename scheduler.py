# -*- coding: utf-8 -*-
"""多模态随心生成 · 任务调度器

核心设计：
- 后台线程扫描 pending 任务
- 启动 subprocess 调用 agnes 脚本
- 阻塞等结果（图片）或轮询 task_id（视频）
- 更新 DB 状态
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any

import config
import db

# ============== 子进程环境变量 ==============
# 强制子进程使用 UTF-8 输出，避免 Windows GBK 报错
SUBPROCESS_ENV = os.environ.copy()
SUBPROCESS_ENV['PYTHONIOENCODING'] = 'utf-8'
SUBPROCESS_ENV['PYTHONUTF8'] = '1'


# ============== ID 生成 ==============
def make_task_id(type_: str) -> str:
    """生成任务 ID：img_<毫秒时间戳>_<4位随机>"""
    import random
    import string
    ts = int(time.time() * 1000)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    prefix = 'img' if type_ == 'image' else ('vid' if type_ == 'video' else 'txt')
    return f'{prefix}_{ts}_{suffix}'


# ============== 日志 ==============
def log(level: str, msg: str):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    # Windows 下 emoji + GBK 坑：强制 ASCII 转义
    # Linux 默认 UTF-8 终端，原样输出
    if sys.platform == 'win32':
        safe_msg = msg.encode('ascii', 'replace').decode('ascii')
    else:
        safe_msg = msg
    try:
        print(f'[{ts}] [{level}] {safe_msg}', flush=True)
    except (OSError, UnicodeEncodeError):
        # 退到 stderr
        try:
            sys.stderr.write(f'[{ts}] [{level}] {safe_msg}\n')
            sys.stderr.flush()
        except Exception:
            pass


# ============== Agnes 脚本调用 ==============
def run_image_task(task: Dict[str, Any]):
    """运行图片任务：subprocess 调 agnes_image_gen.py
    支持 count > 1：循环生成多张，文件名带序号
    """
    task_id = task['id']
    name = task['name']
    prompt = task['prompt']
    params = task.get('params', {})
    model = task['model']
    size = params.get('size', config.DEFAULT_IMAGE_SIZE)
    count = min(params.get('count', config.DEFAULT_IMAGE_COUNT), config.MAX_IMAGE_COUNT)
    custom_name = (params.get('custom_name') or '').strip()
    send_feishu = bool(params.get('send_feishu', False))
    
    # 确保输出目录
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # 基础名称：优先自定义名，fallback 到 task_id
    base_name = custom_name or task_id
    
    log('INFO', f'[{task_id}] 启动图片任务: {name} | {model} | {size} | count={count} | name={base_name}')
    
    # 启动时间
    db.update_task(task_id, status=config.STATUS_RUNNING, started_at=int(time.time() * 1000))
    
    # 收集所有成功生成的文件
    success_files = []
    last_error = None
    
    try:
        for i in range(1, count + 1):
            # 文件名：base_name_1 / base_name_2（单张时省略序号）
            if count == 1:
                file_stem = base_name
            else:
                file_stem = f'{base_name}_{i}'
            
            log('INFO', f'[{task_id}] 生成第 {i}/{count} 张: {file_stem}.png')
            
            # 构建 CLI 命令
            cmd = [
                sys.executable,
                str(config.AGNES_IMAGE_SCRIPT),
                '--prompt', prompt,
                '--size', size,
                '--model', model,
                '--output', f'{file_stem}.png',
                '--output-dir', str(config.IMAGES_DIR),
                '--force',  # 强制重生成（避免与历史缓存冲突）
            ]
            
            # 如果要发飞书，加开关
            if send_feishu:
                cmd.append('--send-feishu')
            
            log('INFO', f'[{task_id}] 执行: {" ".join(cmd[:6])}...')
            
            try:
                result = _run_subprocess_windows(cmd, f'{task_id}_{i}')
            except Exception as inner_e:
                import traceback
                tb = traceback.format_exc()
                log('ERROR', f'[{task_id}] 第 {i} 张 subprocess 异常: {inner_e}\n{tb}')
                last_error = f'第 {i} 张: {inner_e}'
                continue  # 继续下一张
            
            log('INFO', f'[{task_id}] 第 {i} 张退出码: {result.returncode}')
            if result.returncode != 0:
                stderr_text = result.stderr[-500:] if result.stderr else 'empty'
                log('ERROR', f'[{task_id}] 第 {i} 张 stderr: {stderr_text}')
                last_error = f'第 {i} 张: {(result.stderr or result.stdout or "未知错误")[-300:]}'
                continue
            
            # 成功：检查文件
            output_path = config.IMAGES_DIR / f'{file_stem}.png'
            if output_path.exists():
                success_files.append(output_path)
                log('SUCCESS', f'[{task_id}] 第 {i} 张生成成功: {output_path.name}')
            else:
                last_error = f'第 {i} 张生成完成但文件未找到'
                log('ERROR', f'[{task_id}] {last_error}')
        
        # 汇总结果
        if not success_files:
            # 全部失败
            db.update_task(
                task_id,
                status=config.STATUS_FAILED,
                error_msg=last_error or '所有图片生成均失败',
                finished_at=int(time.time() * 1000),
            )
            log('ERROR', f'[{task_id}] 全部 {count} 张生成失败')
            return
        
        # 至少一张成功
        # 读第一张的缓存获取远程 URL（代表作品）
        first_path = success_files[0]
        cache_path = config.IMAGES_DIR / '.agnes_cache' / f'{_prompt_hash(prompt, model, size)}.json'
        remote_url = None
        if cache_path.exists():
            try:
                cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
                remote_url = cache_data.get('remote_url')
            except Exception:
                pass
        
        # 存多个路径用 JSON 数组（数据库里 result_path 仍存主路径，多路径用 result_paths 字段）
        result_paths_json = json.dumps([str(p.relative_to(config.PROJECT_ROOT)) for p in success_files], ensure_ascii=False)
        
        db.update_task(
            task_id,
            status=config.STATUS_SUCCESS,
            result_path=str(first_path.relative_to(config.PROJECT_ROOT)),
            result_url=remote_url,
            result_paths=result_paths_json,
            finished_at=int(time.time() * 1000),
        )
        log('SUCCESS', f'[{task_id}] 图片生成完成: {len(success_files)}/{count} 张成功')
    
    except subprocess.TimeoutExpired:
        db.update_task(
            task_id,
            status=config.STATUS_FAILED,
            error_msg=f'子进程超时（{config.SUBPROCESS_TIMEOUT}秒）',
            finished_at=int(time.time() * 1000),
        )
        log('ERROR', f'[{task_id}] 超时')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.update_task(
            task_id,
            status=config.STATUS_FAILED,
            error_msg=f'调度异常: {str(e)}\n\n{tb[-500:]}',
            finished_at=int(time.time() * 1000),
        )
        log('ERROR', f'[{task_id}] 异常: {e}\n{tb}')


def run_video_task(task: Dict[str, Any]):
    """运行视频任务：subprocess 调 agnes_video_gen.py，异步轮询"""
    task_id = task['id']
    name = task['name']
    prompt = task['prompt']
    params = task.get('params', {})
    model = task['model']
    
    # 默认参数
    width = params.get('width', config.DEFAULT_VIDEO_WIDTH)
    height = params.get('height', config.DEFAULT_VIDEO_HEIGHT)
    num_frames = params.get('num_frames', config.DEFAULT_VIDEO_NUM_FRAMES)
    frame_rate = params.get('frame_rate', config.DEFAULT_VIDEO_FRAME_RATE)
    negative_prompt = params.get('negative_prompt', '')
    
    # 确保输出目录
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    
    log('INFO', f'[{task_id}] 启动视频任务: {name} | {model} | {width}x{height}')
    
    db.update_task(task_id, status=config.STATUS_RUNNING, started_at=int(time.time() * 1000))
    
    try:
        # 构建 CLI 命令
        cmd = [
            sys.executable,
            str(config.AGNES_VIDEO_SCRIPT),
            '--prompt', prompt,
            '--width', str(width),
            '--height', str(height),
            '--num-frames', str(num_frames),
            '--frame-rate', str(frame_rate),
            '--model', model,
        ]
        if negative_prompt:
            cmd.extend(['--negative', negative_prompt])
        
        log('INFO', f'[{task_id}] 执行: {" ".join(cmd[:6])}...')
        
        # 视频任务有 max-wait 参数（默认 900s = 15 分钟）
        cmd.extend(['--max-wait', '900'])
        
        result = None
        try:
            result = _run_subprocess_windows(cmd, task_id)
        except Exception as inner_e:
            import traceback
            tb = traceback.format_exc()
            log('ERROR', f'[{task_id}] 视频 subprocess 异常: {inner_e}\n{tb}')
            raise
        
        log('INFO', f'[{task_id}] 退出码: {result.returncode}')
        if result.returncode != 0:
            log('ERROR', f'[{task_id}] 视频 stderr: {result.stderr[-500:] if result.stderr else "empty"}')
        
        if result.returncode == 0:
            # 成功：解析输出找视频文件
            output_path = _find_latest_video(config.VIDEOS_DIR)
            if output_path:
                db.update_task(
                    task_id,
                    status=config.STATUS_SUCCESS,
                    result_path=str(output_path.relative_to(config.PROJECT_ROOT)),
                    finished_at=int(time.time() * 1000),
                )
                log('SUCCESS', f'[{task_id}] 视频生成成功: {output_path.name}')
            else:
                # 退出 0 但没找到文件 → 可能是复用任务
                db.update_task(
                    task_id,
                    status=config.STATUS_FAILED,
                    error_msg='退出成功但未找到视频文件',
                    finished_at=int(time.time() * 1000),
                )
                log('ERROR', f'[{task_id}] 视频文件未找到')
        else:
            error_msg = (result.stderr or result.stdout or '未知错误')[-500:]
            db.update_task(
                task_id,
                status=config.STATUS_FAILED,
                error_msg=error_msg,
                finished_at=int(time.time() * 1000),
            )
            log('ERROR', f'[{task_id}] 视频生成失败: {error_msg[:200]}')
    
    except subprocess.TimeoutExpired:
        db.update_task(
            task_id,
            status=config.STATUS_FAILED,
            error_msg=f'子进程超时（{config.SUBPROCESS_TIMEOUT}秒）',
            finished_at=int(time.time() * 1000),
        )
        log('ERROR', f'[{task_id}] 视频超时')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.update_task(
            task_id,
            status=config.STATUS_FAILED,
            error_msg=f'调度异常: {str(e)}\n\n{tb[-500:]}',
            finished_at=int(time.time() * 1000),
        )
        log('ERROR', f'[{task_id}] 视频异常: {e}\n{tb}')


# ============== 文本/提示词任务 ==============
def run_text_task(task: Dict[str, Any]):
    """运行文本/提示词生成任务（同步阻塞调 agnes_prompt_gen.py）"""
    task_id = task['id']
    input_text = task.get('input_text') or task.get('prompt') or ''
    input_image = task.get('input_image', '')
    params = task.get('params', {}) or {}
    temperature = params.get('temperature', config.DEFAULT_TEXT_TEMPERATURE)
    max_tokens = params.get('max_tokens', config.DEFAULT_TEXT_MAX_TOKENS)
    enable_thinking = bool(params.get('thinking', False))

    # 子脚本
    py = sys.executable
    output_path = config.TEXTS_DIR / f'{task_id}.txt'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        py, str(config.AGNES_TEXT_SCRIPT),
        '--text', input_text,
        '--temperature', str(temperature),
        '--max-tokens', str(max_tokens),
        '--output', str(output_path),
    ]
    if input_image:
        cmd.extend(['--image', input_image])
    if enable_thinking:
        cmd.append('--thinking')

    db.update_task(task_id, status=config.STATUS_RUNNING, started_at=int(time.time() * 1000))
    log('INFO', f'[{task_id}] 启动文本任务: {task.get("name")} | {task.get("model")} | '
                f'temp={temperature} | max_tokens={max_tokens} | thinking={enable_thinking} | '
                f'image={bool(input_image)}')
    log('INFO', f'[{task_id}] 执行: {" ".join(cmd[:6])}...')

    result = None
    try:
        result = _run_subprocess_windows(cmd, task_id)
    except Exception as inner_e:
        import traceback
        tb = traceback.format_exc()
        log('ERROR', f'[{task_id}] 文本 subprocess 异常: {inner_e}\n{tb}')
        raise

    log('INFO', f'[{task_id}] 退出码: {result.returncode}')
    if result.returncode != 0:
        log('ERROR', f'[{task_id}] 文本 stderr: {result.stderr[-500:] if result.stderr else "empty"}')

    if result.returncode == 0 and output_path.exists():
        content = output_path.read_text(encoding='utf-8').strip()
        if content:
            db.update_task(
                task_id,
                status=config.STATUS_SUCCESS,
                result_text=content,
                result_path=str(output_path.relative_to(config.PROJECT_ROOT)),
                finished_at=int(time.time() * 1000),
            )
            log('SUCCESS', f'[{task_id}] 文本生成成功: {len(content)} 字符')
        else:
            db.update_task(
                task_id,
                status=config.STATUS_FAILED,
                error_msg='退出成功但输出文件为空',
                finished_at=int(time.time() * 1000),
            )
            log('ERROR', f'[{task_id}] 输出文件为空')
    else:
        error_msg = (result.stderr or result.stdout or '未知错误')[-500:] if result else '未获取到结果'
        db.update_task(
            task_id,
            status=config.STATUS_FAILED,
            error_msg=error_msg,
            finished_at=int(time.time() * 1000),
        )
        log('ERROR', f'[{task_id}] 文本生成失败: {error_msg[:200]}')


# ============== 调度器主循环 ==============
class Scheduler:
    """单例调度器"""
    
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
    
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='Scheduler', daemon=True)
        self._thread.start()
        log('INFO', '调度器已启动')
    
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        log('INFO', '调度器已停止')
    
    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                log('ERROR', f'调度循环异常: {e}')
            self._stop.wait(config.SCHEDULER_TICK)
    
    def _tick(self):
        """每轮扫描：调度待执行任务"""
        pending = db.get_pending_tasks(limit=20)
        for task in pending:
            type_ = task['type']
            
            # 并发控制
            running = db.get_running_tasks_by_type(type_)
            if type_ == 'image':
                max_concurrent = config.MAX_IMAGE_CONCURRENCY
            elif type_ == 'video':
                max_concurrent = config.MAX_VIDEO_CONCURRENCY
            else:
                # 文本任务串行执行（避免 prompt gen 占满进程）
                max_concurrent = 1
            if len(running) >= max_concurrent:
                continue
            
            # 启动子线程执行任务
            t = threading.Thread(
                target=_dispatch_task,
                args=(task,),
                name=f'Task-{task["id"]}',
                daemon=True,
            )
            t.start()
            log('INFO', f'调度任务 {task["id"]} ({type_})，当前 {type_} 运行中: {len(running)}/{max_concurrent}')


def _dispatch_task(task: Dict[str, Any]):
    """分派任务到对应执行函数"""
    if task['type'] == 'image':
        run_image_task(task)
    elif task['type'] == 'video':
        run_video_task(task)
    elif task['type'] == 'text':
        run_text_task(task)
    else:
        log('ERROR', f'未知任务类型: {task["type"]} (task_id={task["id"]})')
        db.update_task(task['id'], status=config.STATUS_FAILED,
                       error_msg=f'未知任务类型: {task["type"]}',
                       finished_at=int(time.time() * 1000))



# ============== 工具 ==============
def _run_subprocess_windows(cmd: list, task_id: str) -> subprocess.CompletedProcess:
    """Windows 上可靠地运行子进程

    方案：Popen + 重定向输出到临时文件 + 完全独立（DETACHED_PROCESS）
    """
    import tempfile
    
    stdout_path = Path(tempfile.gettempdir()) / f'multimodal_{task_id}.out'
    stderr_path = Path(tempfile.gettempdir()) / f'multimodal_{task_id}.err'
    
    # 打开输出文件
    stdout_f = open(stdout_path, 'w', encoding='utf-8')
    stderr_f = open(stderr_path, 'w', encoding='utf-8')
    
    try:
        # DETACHED_PROCESS 让子进程完全独立于父进程
        if sys.platform == 'win32':
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            creationflags = 0
        
        proc = subprocess.Popen(
            cmd,
            stdout=stdout_f,
            stderr=stderr_f,
            stdin=subprocess.DEVNULL,
            env=SUBPROCESS_ENV,
            creationflags=creationflags,
            close_fds=True,
        )
        
        try:
            # 视频任务需要更长超时（视频生成 5-10 分钟 + 下载 2-3 分钟）
            # image/text 默认 600 足够
            timeout_sec = 1200 if task_id.startswith('vid_') else config.SUBPROCESS_TIMEOUT
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        
        # 关闭文件句柄后再读
        stdout_f.close()
        stderr_f.close()
        
        stdout_text = stdout_path.read_text(encoding='utf-8', errors='replace') if stdout_path.exists() else ''
        stderr_text = stderr_path.read_text(encoding='utf-8', errors='replace') if stderr_path.exists() else ''
        
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
        )
    finally:
        for f in (stdout_f, stderr_f):
            try: f.close()
            except: pass
        for p in (stdout_path, stderr_path):
            try: p.unlink()
            except: pass


def _prompt_hash(prompt: str, model: str, size: str) -> str:
    """计算 prompt hash（与 agnes_image_gen.py 一致）"""
    import hashlib
    key = f"{model}|{size}|{prompt.strip()}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


def _find_latest_video(dir_: Path) -> Path:
    """找最新生成的视频文件"""
    if not dir_.exists():
        return None
    videos = list(dir_.glob('*.mp4'))
    if not videos:
        return None
    return max(videos, key=lambda p: p.stat().st_mtime)


# ============== 单例 ==============
_scheduler: Scheduler = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
