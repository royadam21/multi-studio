# -*- coding: utf-8 -*-
"""多模态随心生成 · Flask 主入口"""
import sys
import time
from pathlib import Path

# Windows 上强制 UTF-8 避免 GBK 与 emoji 冲突
# Linux 默认 UTF-8 终端，无需 reconfigure
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from flask import Flask, request, jsonify, send_from_directory, render_template, abort

import config
import db
import scheduler

app = Flask(__name__, static_folder='static', template_folder='templates')


# ============== 页面 ==============
@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """静态资源（兜底，生产环境建议用 nginx）"""
    return send_from_directory('static', filename)


# ============== API: 系统 ==============
@app.route('/api/health')
def health():
    return jsonify({'code': 0, 'data': {'status': 'ok'}})


@app.route('/api/models')
def list_models():
    """可用模型列表"""
    type_ = request.args.get('type', 'image')
    models = config.AVAILABLE_MODELS.get(type_, [])
    return jsonify({'code': 0, 'data': {'models': models}})


# ============== API: 任务 ==============
@app.route('/api/tasks', methods=['GET'])
def api_list_tasks():
    """任务列表"""
    type_ = request.args.get('type')  # image / video
    status = request.args.get('status')  # pending / running / success / failed
    limit = int(request.args.get('limit', 100))
    limit = min(limit, 500)
    
    tasks = db.list_tasks(type_=type_, status=status, limit=limit)
    
    # 统计
    total = len(tasks)
    by_status = {}
    for t in tasks:
        by_status[t['status']] = by_status.get(t['status'], 0) + 1
    
    return jsonify({
        'code': 0,
        'data': {
            'tasks': tasks,
            'total': total,
            'by_status': by_status,
        }
    })


@app.route('/api/tasks/<task_id>', methods=['GET'])
def api_get_task(task_id):
    """任务详情"""
    task = db.get_task(task_id)
    if not task:
        return jsonify({'code': 404, 'msg': '任务不存在'}), 404
    return jsonify({'code': 0, 'data': task})


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    """创建任务"""
    data = request.get_json(force=True)
    
    # 必填校验
    name = (data.get('name') or '').strip()
    type_ = data.get('type', 'image')
    model = data.get('model')
    prompt = (data.get('prompt') or '').strip()
    params = data.get('params', {})
    
    if not name:
        return jsonify({'code': 400, 'msg': '任务名不能为空'}), 400
    if type_ not in ('image', 'video', 'text'):
        return jsonify({'code': 400, 'msg': '类型必须是 image / video / text'}), 400
    # text 类型用 input_text 替代 prompt；image/video 必须有 prompt
    if type_ == 'text':
        input_text = (data.get('input_text') or prompt or '').strip()
        if not input_text:
            return jsonify({'code': 400, 'msg': '提示词任务需要 input_text'}), 400
        prompt = input_text  # 写库时复用 prompt 字段
    else:
        if not prompt:
            return jsonify({'code': 400, 'msg': '提示词不能为空'}), 400
    
    # 模型默认
    if not model:
        defaults = [m for m in config.AVAILABLE_MODELS.get(type_, []) if m.get('default')]
        if defaults:
            model = defaults[0]['id']
        else:
            # 兜底：按 type 拿第一个；最后才回落到 image
            fallback_pool = config.AVAILABLE_MODELS.get(type_, []) or config.AVAILABLE_MODELS.get('image', [])
            if fallback_pool:
                model = fallback_pool[0]['id']
            else:
                return jsonify({'code': 400, 'msg': '该类型暂无可用模型'}), 400
    
    # 校验模型
    valid_models = [m['id'] for m in config.AVAILABLE_MODELS.get(type_, [])]
    if model not in valid_models:
        return jsonify({'code': 400, 'msg': f'模型 {model} 不支持该类型'}), 400
    
    # 校验图片尺寸
    if type_ == 'image' and 'size' in params:
        if params['size'] not in config.SUPPORTED_IMAGE_SIZES:
            return jsonify({'code': 400, 'msg': f'尺寸 {params["size"]} 不支持'}), 400
    
    # 生成 ID + 写库
    task_id = scheduler.make_task_id(type_)
    task = db.create_task(
        task_id, name, type_, model, prompt, params,
        input_text=input_text if type_ == 'text' else None,
        input_image=(data.get('input_image') or None) if type_ == 'text' else None,
    )
    
    return jsonify({'code': 0, 'data': task})


@app.route('/api/tasks/<task_id>/retry', methods=['POST'])
def api_retry_task(task_id):
    """重试失败任务"""
    task = db.get_task(task_id)
    if not task:
        return jsonify({'code': 404, 'msg': '任务不存在'}), 404
    if task['status'] != config.STATUS_FAILED:
        return jsonify({'code': 400, 'msg': f'只能重试失败任务，当前状态: {task["status"]}'}), 400
    
    # 重置为 pending
    db.update_task(
        task_id,
        status=config.STATUS_PENDING,
        error_msg=None,
        started_at=None,
        finished_at=None,
        result_path=None,
        result_url=None,
        remote_task_id=None,
    )
    
    return jsonify({'code': 0, 'data': db.get_task(task_id)})


@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    """删除任务"""
    task = db.get_task(task_id)
    if not task:
        return jsonify({'code': 404, 'msg': '任务不存在'}), 404
    
    # 删文件（单 + 多）
    paths_to_delete = []
    rp = task.get('result_paths')
    if rp and isinstance(rp, list):
        paths_to_delete.extend(rp)
    if task.get('result_path'):
        paths_to_delete.append(task['result_path'])
    # 去重
    paths_to_delete = list(dict.fromkeys(paths_to_delete))
    
    for rel_path in paths_to_delete:
        try:
            file_path = config.PROJECT_ROOT / rel_path
            if file_path.exists():
                file_path.unlink()
                sys.stdout.write(f'已删除文件: {file_path}\n')
        except Exception as e:
            sys.stdout.write(f'删除文件失败: {e}\n')
    
    # 删 DB
    db.delete_task(task_id)
    
    return jsonify({'code': 0, 'data': {'deleted': task_id}})


@app.route('/api/tasks/<task_id>/result')
def api_get_result(task_id):
    """获取结果文件（图片/视频）
    支持查询参数 ?index=0 取多文件中的某一个（0 默认）
    """
    task = db.get_task(task_id)
    if not task:
        abort(404)
    if not task.get('result_path'):
        abort(404)
    
    # 多文件模式：有 result_paths 数组 + index 参数
    idx = request.args.get('index', 0, type=int)
    rp = task.get('result_paths')
    if rp and isinstance(rp, list) and 0 <= idx < len(rp):
        rel_path = rp[idx]
    else:
        rel_path = task['result_path']
    
    file_path = config.PROJECT_ROOT / rel_path
    if not file_path.exists():
        abort(404)
    
    return send_from_directory(file_path.parent, file_path.name)


# ============== 本地图床（text 任务参考图）==============
ALLOWED_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

@app.route('/api/upload/image', methods=['POST'])
def api_upload_image():
    """上传参考图到 tasks/texts/_refs/，返回可访问的 URL"""
    if 'file' not in request.files:
        return jsonify({'code': 400, 'msg': '未提供文件字段 "file"'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'code': 400, 'msg': '文件名为空'}), 400

    # 校验后缀
    ext = ('.' + f.filename.rsplit('.', 1)[-1].lower()) if '.' in f.filename else ''
    if ext not in ALLOWED_IMAGE_EXTS:
        return jsonify({'code': 400, 'msg': f'不支持的文件格式 {ext}（仅 png/jpg/jpeg/webp）'}), 400

    # 校验大小
    f.seek(0, 2)  # 移到末尾
    size = f.tell()
    f.seek(0)
    if size > MAX_UPLOAD_SIZE:
        return jsonify({'code': 400, 'msg': f'文件超过 10MB（{size // 1024}KB）'}), 400

    # 存到 tasks/texts/_refs/ref_<ts>_<rand>.<ext>
    ref_dir = config.TEXTS_DIR / '_refs'
    ref_dir.mkdir(parents=True, exist_ok=True)
    import uuid
    fname = f'ref_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}{ext}'
    save_path = ref_dir / fname
    f.save(save_path)

    # 返回可访问 URL + 本地路径（供 scheduler 透传给 agnes 脚本）
    rel = str(save_path.relative_to(config.PROJECT_ROOT))  # tasks/texts/_refs/ref_xxx.png
    url = f'/refs/{fname}'  # 由 /refs/<filename> 路由提供预览
    return jsonify({'code': 0, 'data': {'url': url, 'path': rel, 'size': size, 'name': fname}})


@app.route('/refs/<filename>')
def api_serve_ref(filename):
    """提供本地图床访问（只读、限定 _refs/ 目录）"""
    return send_from_directory(config.TEXTS_DIR / '_refs', filename)


# ============== 错误处理 ==============
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'code': 404, 'msg': 'Not Found'}), 404
    return render_template('index.html')  # SPA fallback


@app.errorhandler(500)
def server_error(e):
    return jsonify({'code': 500, 'msg': 'Internal Server Error'}), 500


# ============== 启动 ==============
def main():
    # 初始化
    db.init_db()
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 启动调度器
    sched = scheduler.get_scheduler()
    sched.start()
    
    # 启动 Flask
    print(f'=' * 60, flush=True)
    print(f'🎨 多模态随心生成 启动中...', flush=True)
    print(f'   访问: http://{config.HOST}:{config.PORT}', flush=True)
    print(f'   数据库: {config.DB_PATH}', flush=True)
    print(f'   图片输出: {config.IMAGES_DIR}', flush=True)
    print(f'   视频输出: {config.VIDEOS_DIR}', flush=True)
    print(f'=' * 60, flush=True)
    
    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, use_reloader=False, threaded=True)
    finally:
        sched.stop()


if __name__ == '__main__':
    main()
