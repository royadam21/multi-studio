# -*- coding: utf-8 -*-
"""多模态随心生成 · SQLite 封装"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

import config


# ============== 初始化 ==============
def init_db():
    """创建表结构"""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                type            TEXT NOT NULL,
                model           TEXT NOT NULL,
                prompt          TEXT NOT NULL,
                params          TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL,
                remote_task_id  TEXT,
                result_path     TEXT,
                result_url      TEXT,
                error_msg       TEXT,
                created_at      INTEGER NOT NULL,
                started_at      INTEGER,
                finished_at     INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_type_created ON tasks(type, created_at DESC);
        ''')
        # 迁移：添加 result_paths 字段（存多文件 JSON 数组）
        try:
            conn.execute('ALTER TABLE tasks ADD COLUMN result_paths TEXT')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        # 迁移：添加文本任务的输入输出字段
        for col, typedef in [
            ('input_text', 'TEXT'),       # 文本任务的输入文本（与 prompt 互补：prompt 是任务描述，input_text 是用户原始需求）
            ('input_image', 'TEXT'),     # 文本任务的可选参考图片 URL 或 data URL
            ('result_text', 'TEXT'),     # 文本任务的输出文本
        ]:
            try:
                conn.execute(f'ALTER TABLE tasks ADD COLUMN {col} {typedef}')
            except sqlite3.OperationalError:
                pass  # 字段已存在


@contextmanager
def get_conn():
    """上下文管理连接"""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ============== CRUD ==============
def create_task(task_id: str, name: str, type_: str, model: str, prompt: str,
                params: Dict[str, Any], status: str = config.STATUS_PENDING,
                input_text: str = '', input_image: str = '') -> Dict[str, Any]:
    """创建任务"""
    now = int(time.time() * 1000)
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO tasks (id, name, type, model, prompt, params, status, created_at, input_text, input_image)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (task_id, name, type_, model, prompt, json.dumps(params, ensure_ascii=False), status, now,
             input_text, input_image)
        )
    return get_task(task_id)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务"""
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_tasks(type_: Optional[str] = None, status: Optional[str] = None,
               limit: int = 100) -> List[Dict[str, Any]]:
    """任务列表"""
    sql = 'SELECT * FROM tasks WHERE 1=1'
    params = []
    if type_:
        sql += ' AND type = ?'
        params.append(type_)
    if status:
        sql += ' AND status = ?'
        params.append(status)
    sql += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def update_task(task_id: str, **fields) -> Optional[Dict[str, Any]]:
    """更新任务字段（白名单保护）"""
    if not fields:
        return get_task(task_id)
    
    # 白名单：只允许更新这些列
    ALLOWED_COLUMNS = {
        'name', 'type', 'model', 'prompt', 'params', 'status',
        'remote_task_id', 'result_path', 'result_url', 'result_paths',
        'error_msg', 'started_at', 'finished_at',
        'input_text', 'input_image', 'result_text',
    }
    safe_fields = {k: v for k, v in fields.items() if k in ALLOWED_COLUMNS}
    if not safe_fields:
        return get_task(task_id)
    
    # 序列化 params（如果是 dict）
    if 'params' in safe_fields and isinstance(safe_fields['params'], dict):
        safe_fields['params'] = json.dumps(safe_fields['params'], ensure_ascii=False)
    
    set_clause = ', '.join(f'{k} = ?' for k in safe_fields.keys())
    values = list(safe_fields.values()) + [task_id]
    with get_conn() as conn:
        conn.execute(f'UPDATE tasks SET {set_clause} WHERE id = ?', values)
    return get_task(task_id)


def delete_task(task_id: str) -> bool:
    """删除任务"""
    with get_conn() as conn:
        cur = conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        return cur.rowcount > 0


def get_pending_tasks(limit: int = 10) -> List[Dict[str, Any]]:
    """获取待执行任务（按创建时间排序）"""
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC LIMIT ?',
            (config.STATUS_PENDING, limit)
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_running_tasks_by_type(type_: str) -> List[Dict[str, Any]]:
    """获取运行中的某类型任务（用于并发控制）"""
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE status = ? AND type = ?',
            (config.STATUS_RUNNING, type_)
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ============== 辅助 ==============
def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """sqlite3.Row → dict，解析 params JSON"""
    if row is None:
        return None
    d = dict(row)
    # 解析 params
    try:
        d['params'] = json.loads(d.get('params') or '{}')
    except (json.JSONDecodeError, TypeError):
        d['params'] = {}
    # 解析 result_paths（多文件 JSON 数组）
    try:
        rp = d.get('result_paths')
        d['result_paths'] = json.loads(rp) if rp else None
    except (json.JSONDecodeError, TypeError):
        d['result_paths'] = None
    # 计算 duration
    if d.get('started_at') and d.get('finished_at'):
        d['duration_ms'] = d['finished_at'] - d['started_at']
    else:
        d['duration_ms'] = None
    return d
