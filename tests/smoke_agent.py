"""B 模块端到端冒烟：登录后依次调用智能体接口。

运行（仓库根目录）：python tests/smoke_agent.py
输出：tests/_smoke_out.txt（UTF-8，含各接口响应摘要）
"""
from __future__ import annotations

import json
import os
import atexit
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Always isolate this demonstration from local user data and model credentials.
(ROOT / '.tmp').mkdir(exist_ok=True)
_database = tempfile.TemporaryDirectory(prefix='agent-smoke-', dir=ROOT / '.tmp')
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_database.name) / 'smoke.db').as_posix()
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'true'

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from backend.app.platform.database import engine  # noqa: E402


def cleanup() -> None:
    engine.dispose()
    _database.cleanup()


atexit.register(cleanup)

HEADERS = {'X-Requested-With': 'shuban-web'}
# 一像素 PNG：契约要求识别入参必须是真实图片，演示模式下才由模式层返回 503。
PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAA'
           'SUVORK5CYII=')
lines: list[str] = []
summary: list[str] = []


def record(title: str, status: int, payload=None) -> None:
    assert status == (503 if 'recognize' in title else 200), (title, status)
    summary.append(f'{title}: HTTP {status}')
    lines.append(f'--- {title} --- HTTP {status}')
    if payload is not None:
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2)[:1500])


with TestClient(app) as client:
    response = client.post('/api/auth/login', json={'username': 'student', 'password': 'Student123!', 'role': 'student'}, headers=HEADERS)
    summary.append(f'login: HTTP {response.status_code}')
    assert response.status_code == 200

    response = client.get('/api/agent/status')
    record('GET /api/agent/status', response.status_code, response.json())

    response = client.post('/api/agent/ask', json={'question': '什么是函数在一点连续？', 'topic': '函数与极限'}, headers=HEADERS)
    data = response.json()
    record('POST /api/agent/ask', response.status_code, {
        'mode': data.get('mode'), 'notice': data.get('notice'),
        'answer': data.get('answer', '')[:240], 'references': data.get('references'),
    })

    response = client.post('/api/agent/feedback', json={
        'question': '求 lim(x→0) sin(x)/x',
        'step': '我直接用洛必达法则求导',
        'steps': ['先判断是 0/0 型'],
    }, headers=HEADERS)
    record('POST /api/agent/feedback', response.status_code, response.json())

    response = client.post('/api/agent/diagnosis', json={
        'question': '洛必达法则怎么用？',
        'answer': '我直接代入得到 0/0 就用了洛必达',
        'wrong_points': ['导数'],
    }, headers=HEADERS)
    data = response.json()
    record('POST /api/agent/diagnosis', response.status_code, {
        'mode': data.get('mode'), 'weak_points': data.get('weak_points'),
        'suggested_practice': [item['title'] for item in data.get('suggested_practice', [])],
        'summary': data.get('summary'), 'next_step': data.get('next_step'),
    })

    response = client.post('/api/agent/recognize', json={'image_base64': PNG_1PX}, headers=HEADERS)
    record('POST /api/agent/recognize (预期 503)', response.status_code, response.json())

    response = client.post('/api/conversations', json={'question': '求 lim(x→0) sin(x)/x 的极限', 'topic': '函数与极限'}, headers=HEADERS)
    data = response.json()
    summary.append(f'POST /api/conversations: HTTP {response.status_code} mode={data.get("mode")} refs={len(data.get("references", []))}')
    assert response.status_code == 201 and data['mode'] == 'demo'

    with client.stream('POST', '/api/agent/ask/stream', json={'question': '导数的几何意义是什么？'}, headers=HEADERS) as stream:
        events = [line for line in stream.iter_lines() if line.startswith('data:')]
    summary.append(f'SSE /api/agent/ask/stream: HTTP {stream.status_code} events={len(events)}')
    assert stream.status_code == 200 and len(events) >= 3
    lines.append('--- SSE 事件 ---')
    lines.extend(events[:6])

    # ---- 第二阶段：长期记忆 / 推荐 / 评价 / 总结 / 资源检索 ----
    response = client.post('/api/agent/review', json={
        'text': '定积分是区间上求和取极限，几何意义是曲线与 x 轴围成的面积，可以用牛顿-莱布尼茨公式计算。',
        'topic': '一元函数积分学',
    }, headers=HEADERS)
    data = response.json()
    record('POST /api/agent/review', response.status_code, {
        'band': data.get('band'), 'coverage': data.get('coverage'),
        'point': (data.get('point') or {}).get('title'),
        'signals_missing': data.get('signals_missing'), 'method': data.get('method'),
    })
    assert response.status_code == 200 and data['band'] in {'基本到位', '有遗漏', '需要重讲'}
    assert data['mode'] == 'demo'

    response = client.get('/api/agent/memory', headers=HEADERS)
    data = response.json()
    summary.append(f'GET /api/agent/memory: HTTP {response.status_code} events={data.get("event_count")} kinds={sorted(data.get("kinds", {}))}')
    assert response.status_code == 200 and data['event_count'] >= 1

    response = client.post('/api/agent/recommend', json={'limit': 3}, headers=HEADERS)
    data = response.json()
    record('POST /api/agent/recommend', response.status_code, {
        'topic': data.get('topic'),
        'items': [{'point_id': item['point_id'], 'reason': item['reason']} for item in data.get('items', [])],
    })
    assert response.status_code == 200 and data['items']

    response = client.post('/api/agent/summary', json={'days': 7}, headers=HEADERS)
    data = response.json()
    record('POST /api/agent/summary', response.status_code, {
        'period_days': data.get('period_days'), 'question_count': data.get('question_count'),
        'highlights': data.get('highlights'), 'next_steps': data.get('next_steps'),
    })
    assert response.status_code == 200 and data['next_steps']

    response = client.post('/api/agent/resources/search', json={'query': '定积分 面积'}, headers=HEADERS)
    data = response.json()
    summary.append(f'POST /api/agent/resources/search: HTTP {response.status_code} items={data.get("total")}')
    assert response.status_code == 200 and data['items']

(HERE.parent / '_smoke_out.txt').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(summary))
