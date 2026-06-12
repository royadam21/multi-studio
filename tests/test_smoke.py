# -*- coding: utf-8 -*-
"""多模态随心生成 · 冒烟测试

需要服务已启动 (py -3 app.py)
"""
import sys
import time
import json
import requests

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:5000'


def test(name, fn):
    try:
        fn()
        print(f'  ✅ {name}')
        return True
    except Exception as e:
        print(f'  ❌ {name}: {e}')
        return False


def main():
    print('=' * 60)
    print('🧪 多模态随心生成 · 冒烟测试')
    print('=' * 60)
    print(f'目标: {BASE}')
    print()
    
    passed = 0
    total = 0
    
    # 1. 健康检查
    total += 1
    def t1():
        r = requests.get(f'{BASE}/api/health', timeout=5)
        assert r.status_code == 200
        assert r.json()['code'] == 0
    if test('健康检查 /api/health', t1): passed += 1
    
    # 2. 模型列表
    total += 1
    def t2():
        r = requests.get(f'{BASE}/api/models?type=image', timeout=5)
        assert r.status_code == 200
        models = r.json()['data']['models']
        assert len(models) > 0
        assert any(m['id'] == 'agnes-image-2.1-flash' for m in models)
    if test('图片模型列表 /api/models?type=image', t2): passed += 1
    
    # 3. 视频模型
    total += 1
    def t3():
        r = requests.get(f'{BASE}/api/models?type=video', timeout=5)
        assert r.status_code == 200
        models = r.json()['data']['models']
        assert any(m['id'] == 'agnes-video-v2.0' for m in models)
    if test('视频模型列表 /api/models?type=video', t3): passed += 1
    
    # 4. 任务列表（空）
    total += 1
    def t4():
        r = requests.get(f'{BASE}/api/tasks?type=image', timeout=5)
        assert r.status_code == 200
        data = r.json()['data']
        assert 'tasks' in data
        assert 'total' in data
    if test('图片任务列表 /api/tasks?type=image', t4): passed += 1
    
    # 5. 创建任务
    total += 1
    def t5():
        payload = {
            'name': '冒烟测试_小猫',
            'type': 'image',
            'model': 'agnes-image-2.1-flash',
            'prompt': 'A cute orange kitten sitting on a bamboo mat, watercolor style',
            'params': {'size': '1024x1024', 'count': 1},
        }
        r = requests.post(f'{BASE}/api/tasks', json=payload, timeout=10)
        assert r.status_code == 200
        data = r.json()['data']
        assert data['id'].startswith('img_')
        assert data['status'] in ('pending', 'running')
        # 保存任务 ID 供下一步用
        global TEST_TASK_ID
        TEST_TASK_ID = data['id']
    if test('创建图片任务 POST /api/tasks', t5): passed += 1
    
    # 6. 查询任务
    total += 1
    def t6():
        r = requests.get(f'{BASE}/api/tasks/{TEST_TASK_ID}', timeout=5)
        assert r.status_code == 200
        task = r.json()['data']
        assert task['id'] == TEST_TASK_ID
    if test('查询任务 /api/tasks/<id>', t6): passed += 1
    
    # 7. 等待任务完成（图片通常 15-30 秒）
    total += 1
    def t7():
        print('    ⏳ 等待任务完成（最长 60 秒）...', end=' ', flush=True)
        start = time.time()
        while time.time() - start < 60:
            r = requests.get(f'{BASE}/api/tasks/{TEST_TASK_ID}', timeout=5)
            task = r.json()['data']
            if task['status'] in ('success', 'failed'):
                elapsed = time.time() - start
                print(f'完成 ({task["status"]}, {elapsed:.1f}s)')
                assert task['status'] == 'success', f'任务失败: {task.get("error_msg")}'
                return
            time.sleep(2)
        raise TimeoutError('任务 60 秒未完成')
    if test('任务执行完成（轮询）', t7): passed += 1
    
    # 8. 访问结果文件
    total += 1
    def t8():
        r = requests.get(f'{BASE}/api/tasks/{TEST_TASK_ID}/result', timeout=10)
        assert r.status_code == 200
        assert len(r.content) > 1000  # 至少 1KB
    if test('访问结果文件 /api/tasks/<id>/result', t8): passed += 1
    
    # 9. 删除任务
    total += 1
    def t9():
        r = requests.delete(f'{BASE}/api/tasks/{TEST_TASK_ID}', timeout=5)
        assert r.status_code == 200
        # 验证已删
        r = requests.get(f'{BASE}/api/tasks/{TEST_TASK_ID}', timeout=5)
        assert r.status_code == 404
    if test('删除任务 DELETE /api/tasks/<id>', t9): passed += 1
    
    # 10. 主页能渲染
    total += 1
    def t10():
        r = requests.get(f'{BASE}/', timeout=5)
        assert r.status_code == 200
        assert '多模态随心生成' in r.text
    if test('主页 GET /', t10): passed += 1
    
    # 汇总
    print()
    print('=' * 60)
    print(f'结果: {passed}/{total} 通过')
    if passed == total:
        print('🎉 全部通过！')
    else:
        print(f'⚠️  {total - passed} 个失败')
    print('=' * 60)
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
