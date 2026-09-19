"""Authentication, role boundaries, persistence, and the real assignment loop."""
from datetime import date, timedelta
from pathlib import Path
import tempfile

# Independent of module import order: never reuse the configured application engine.
_test_db = tempfile.TemporaryDirectory(prefix='shuban-tests-')

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app import main
from backend.app.platform import database as database_module
from backend.app.main import app
from backend.app.platform.database import Base, User, Session, Conversation
from backend.app.platform.auth import token_hash

engine = create_engine(f'sqlite:///{Path(_test_db.name) / "test.db"}', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

HEADERS = {'X-Requested-With': 'shuban-web'}


def test_demo_disables_recognition_even_with_credentials(client, monkeypatch):
    from backend.app.ai import service
    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('MODEL_API_KEY', 'synthetic-key')
    monkeypatch.setenv('MODEL_NAME', 'test-model')
    def must_not_call(*args, **kwargs):
        raise AssertionError('Demo mode must never call the model')
    monkeypatch.setattr(service, 'chat', must_not_call)
    login(client)
    assert client.get('/api/agent/status').json()['capabilities']['recognize'] is False
    assert client.post('/api/agent/recognize', json={'image_base64': 'a' * 16}).status_code == 503


def test_live_reply_fallback_history_and_health(client, monkeypatch):
    from backend.app.ai import service
    from backend.app.ai.llm import ModelCallFailed
    monkeypatch.setenv('AGENT_MODE', 'live')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('MODEL_API_KEY', 'synthetic-key')
    monkeypatch.setenv('MODEL_NAME', 'test-model')
    monkeypatch.setattr(service, 'chat', lambda *a, **kw: '模型模拟返回：这里提及“未连接真实模型”只是引用，不改变来源。')
    login(client)
    assert client.get('/api/health').json()['agent_mode'] == 'live'
    live = client.post('/api/conversations', json={'question': '可导与连续'}).json()
    assert live['mode'] == 'live' and live['references']
    assert not live['references'][0]['verified']
    def unavailable(*args, **kwargs):
        raise ModelCallFailed('网络连接失败或超时。')
    monkeypatch.setattr(service, 'chat', unavailable)
    fallback = client.post('/api/conversations', json={'question': '用定义求导数'}).json()
    assert fallback['mode'] == 'demo' and fallback['notice']
    client.post('/api/auth/logout')
    login(client)
    history = client.get('/api/conversations').json()
    saved = next(x for x in history if x['id'] == fallback['id'])
    assert saved['mode'] == 'demo' and '调用提示' in saved['answer']
    assert next(x for x in history if x['id'] == live['id'])['mode'] == 'live'


@pytest.fixture(scope='session', autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    _test_db.cleanup()


@pytest.fixture(autouse=True)
def database(monkeypatch):
    monkeypatch.setenv('SHUBAN_SEED_DEMO', 'true')
    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'SessionLocal', SessionLocal)
    monkeypatch.setattr(database_module, 'engine', engine)
    monkeypatch.setattr(database_module, 'SessionLocal', SessionLocal)
    Base.metadata.drop_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app, headers=HEADERS) as c:
        yield c


def login(client, role='student', remember=False):
    return client.post('/api/auth/login', json={'username': role, 'password': f'{role.title()}123!', 'role': role, 'remember': remember})


@pytest.mark.parametrize('role', ['student', 'teacher'])
def test_login_and_role(client, role):
    response = login(client, role)
    assert response.status_code == 200
    assert response.json()['role'] == role
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=strict' in response.headers['set-cookie'].lower()
    assert 'max-age' not in response.headers['set-cookie'].lower()
    assert client.get('/api/auth/me').json()['role'] == role


def test_bad_password_or_role(client):
    assert client.post('/api/auth/login', json={'username': 'student', 'password': 'wrong', 'role': 'student'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'student', 'password': 'Student123!', 'role': 'teacher'}).status_code == 401
    assert client.get('/api/conversations').status_code == 401
    assert client.get('/api/assignments').status_code == 401


def test_remember_and_logout_revokes_token(client):
    assert 'Max-Age=604800' in login(client, remember=True).headers['set-cookie']
    old = client.cookies.get('shuxue_session')
    assert client.post('/api/auth/logout').status_code == 200
    client.cookies.set('shuxue_session', old)
    assert client.get('/api/auth/me').status_code == 401
    with SessionLocal() as db:
        assert not db.get(Session, token_hash(old))


def test_expired_session(client):
    login(client)
    with SessionLocal() as db:
        session = db.get(Session, token_hash(client.cookies.get('shuxue_session')))
        session.expires = 1
        db.commit()
    assert client.get('/api/auth/me').status_code == 401


def test_new_login_revokes_old_cookie(client):
    login(client)
    old = client.cookies.get('shuxue_session')
    login(client, 'teacher')
    with SessionLocal() as db:
        assert not db.get(Session, token_hash(old))


def test_password_not_stored_in_plaintext(client):
    with SessionLocal() as db:
        assert db.get(User, 'student').password_hash != 'Student123!'
        assert 'Student123!' not in db.get(User, 'student').password_hash


def test_chat_saved_favorite_and_private(client):
    login(client)
    response = client.post('/api/conversations', json={'question': '用定义求 x² 的导数', 'topic': '导数与微分'})
    assert response.status_code == 201
    item = response.json()
    assert item['mode'] == 'demo' and '固定例题' in item['answer']
    assert client.patch(f'/api/conversations/{item["id"]}', json={'favorite': True}).json()['favorite']
    client.post('/api/auth/logout')
    login(client)
    assert client.get('/api/conversations').json()[0]['favorite']
    with SessionLocal() as db:
        assert db.get(Conversation, item['id']).question == item['question']
    login(client, 'teacher')
    assert client.get('/api/conversations').json() == []
    assert client.patch(f'/api/conversations/{item["id"]}', json={'favorite': False}).status_code == 404


def test_unknown_question_not_fabricated(client):
    login(client)
    result = client.post('/api/conversations', json={'question': '请证明一个新定理'}).json()
    assert '还不能生成' in result['answer']


def test_assignments_round_trip_and_role_guard(client):
    login(client, 'teacher')
    response = client.post('/api/assignments', json={'class_id': 'demo-class', 'title': '测试作业', 'content': '解释导数', 'topic': '导数与微分', 'due_date': (date.today() + timedelta(days=1)).isoformat()})
    assert response.status_code == 201
    assignment_id = response.json()['id']
    assert client.put(f'/api/assignments/{assignment_id}/submission', json={'answer': '1'}).status_code == 403
    login(client)
    assert client.post('/api/assignments', json={'title': 'x', 'content': 'x', 'topic': 'x', 'due_date': date.today().isoformat()}).status_code == 403
    for answer in ['第一次作答', '修改后的作答']:
        response = client.put(f'/api/assignments/{assignment_id}/submission', json={'answer': answer})
        assert response.status_code == 200 and response.json()['submitted']
    assert 'submissions' not in response.json()
    login(client, 'teacher')
    saved = next(a for a in client.get('/api/assignments').json() if a['id'] == assignment_id)
    assert len(saved['submissions']) == 1
    assert saved['submissions'][0]['answer'] == '修改后的作答'


def test_validation_and_csrf(client):
    login(client)
    assert client.post('/api/conversations', json={'question': '   '}).status_code == 422
    assert client.post('/api/conversations', json={'question': 'x' * 2001}).status_code == 422
    assert client.put('/api/assignments/missing/submission', json={'answer': 'x'}).status_code == 404
    assert client.post('/api/auth/logout', headers={'X-Requested-With': ''}).status_code == 403
    login(client, 'teacher')
    assert client.post('/api/assignments', json={'title': 'x', 'content': 'x', 'topic': 'x', 'due_date': '2020-01-01'}).status_code == 422


def test_draft_lifecycle_and_student_visibility(client):
    login(client, 'teacher')
    draft = client.post('/api/assignments/drafts', json={}).json()
    aid = draft['id']
    assert draft['status'] == 'draft' and draft['due_date'] == ''
    assert client.post(f'/api/assignments/{aid}/publish').status_code == 422
    login(client)
    assert aid not in [a['id'] for a in client.get('/api/assignments').json()]
    assert client.put(f'/api/assignments/{aid}/submission', json={'answer': 'x'}).status_code == 404
    assert client.post('/api/assignments/drafts', json={}).status_code == 403
    login(client, 'teacher')
    fields = {'class_id': 'demo-class', 'title': '草稿发布', 'content': '题干 $x^2$', 'topic': '导数与微分', 'due_date': date.today().isoformat()}
    assert client.patch(f'/api/assignments/{aid}', json=fields).status_code == 200
    for _ in range(2):
        assert client.post(f'/api/assignments/{aid}/publish').json()['status'] == 'published'
    assert client.patch(f'/api/assignments/{aid}', json={'content': 'changed'}).status_code == 409
    assert client.patch(f'/api/assignments/{aid}', json={'due_date': (date.today() - timedelta(days=1)).isoformat()}).status_code == 409
    assert client.patch(f'/api/assignments/{aid}', json={'due_date': (date.today() + timedelta(days=1)).isoformat()}).status_code == 200
    assert client.delete(f'/api/assignments/{aid}').status_code == 409
    copied = client.post(f'/api/assignments/{aid}/copy').json()
    assert copied['id'] != aid and copied['status'] == 'draft' and copied['due_date'] == '' and not copied['submissions']
    assert client.delete(f'/api/assignments/{copied["id"]}').status_code == 200
    ids = [a['id'] for a in client.get('/api/assignments').json()]
    assert ids.count(aid) == 1 and copied['id'] not in ids
    login(client)
    assert client.put(f'/api/assignments/{aid}/submission', json={'answer': 'before archive'}).status_code == 200
    login(client, 'teacher')
    for _ in range(2):
        assert client.post(f'/api/assignments/{aid}/archive').json()['status'] == 'archived'
    assert client.post(f'/api/assignments/{aid}/publish').status_code == 409
    assert client.patch(f'/api/assignments/{aid}', json={'title': 'x'}).status_code == 409
    login(client)
    assert client.put(f'/api/assignments/{aid}/submission', json={'answer': 'after archive'}).status_code == 409
    stored = next(a for a in client.get('/api/assignments').json() if a['id'] == aid)
    assert stored['answer'] == 'before archive' and stored['status'] == 'archived'


def test_questions_snapshot_order_search_and_secrecy(client):
    login(client, 'teacher')
    q1 = client.post('/api/questions', json={'title': '导数题', 'topic': '导数与微分', 'content': '求导 $x^2$', 'reference_answer': 'PRIVATE-REFERENCE'}).json()
    q2 = client.post('/api/questions', json={'title': '极限题', 'topic': '函数与极限', 'content': '解释极限'}).json()
    assert len(client.get('/api/questions', params={'search': '求导', 'topic': '导数与微分'}).json()) == 1
    assert client.get('/api/questions', params={'search': '%'}).json() == []
    draft = client.post('/api/assignments/drafts', json={'question_ids': [q2['id'], q1['id']]}).json()
    assert draft['content'] == '1. 解释极限\n\n2. 求导 $x^2$'
    assert 'PRIVATE-REFERENCE' not in str(draft)
    assert client.post('/api/assignments/drafts', json={'question_ids': [q1['id'], q1['id']]}).status_code == 422
    assert client.patch(f'/api/questions/{q1["id"]}', json={'content': 'new content'}).status_code == 200
    assert next(a for a in client.get('/api/assignments').json() if a['id'] == draft['id'])['content'] == draft['content']
    for _ in range(2):
        assert client.post(f'/api/questions/{q1["id"]}/archive').status_code == 200
    assert len(client.get('/api/questions', params={'archived': True}).json()) == 1
    assert client.patch(f'/api/questions/{q1["id"]}', json={'title': 'new title'}).status_code == 409
    assert client.post('/api/assignments/drafts', json={'question_ids': [q1['id']]}).status_code == 409
    aid = draft['id']
    client.patch(f'/api/assignments/{aid}', json={'class_id': 'demo-class', 'title': '题库作业', 'topic': '混合', 'due_date': date.today().isoformat()})
    assert client.post(f'/api/assignments/{aid}/publish').status_code == 200
    login(client)
    assert client.get('/api/questions').status_code == 403
    assert client.get('/api/teaching/stats').status_code == 403
    assert 'PRIVATE-REFERENCE' not in client.get('/api/assignments').text


def test_review_revisions_statistics_and_history(client):
    login(client, 'teacher')
    aid = client.post('/api/assignments', json={'class_id': 'demo-class', 'title': '版本测试', 'topic': '导数', 'content': '求导', 'due_date': date.today().isoformat()}).json()['id']
    url = f'/api/assignments/{aid}/submissions/student/review'
    payload = {'version': 1, 'comment': '请补充过程', 'status': 'needs_improvement'}
    assert client.put(url, json=payload).status_code == 404
    baseline = client.get('/api/teaching/stats').json()
    login(client)
    initial = client.put(f'/api/assignments/{aid}/submission', json={'answer': '第一版'}).json()['submission']
    assert initial['version'] == 1 and initial['review'] is None
    assert client.put(url, json=payload).status_code == 403
    login(client, 'teacher')
    assert client.get('/api/teaching/stats').json()['pending'] == 1
    assert client.put(url, json=payload).status_code == 200
    payload['comment'] = '请写出定义'
    assert client.put(url, json=payload).status_code == 200
    assert client.get('/api/teaching/stats').json()['needs_improvement'] == 1
    login(client)
    item = next(a for a in client.get('/api/assignments').json() if a['id'] == aid)
    assert item['submission']['review']['comment'] == '请写出定义'
    latest = client.put(f'/api/assignments/{aid}/submission', json={'answer': '第二版'}).json()['submission']
    assert latest['id'] == initial['id'] and latest['version'] == 2 and latest['review'] is None
    assert len(latest['review_history']) == 1 and latest['review_history'][0]['answer_snapshot'] == '第一版'
    login(client, 'teacher')
    assert client.put(url, json=payload).status_code == 409
    pending = client.get('/api/teaching/stats').json()
    assert pending['pending'] == 1 and pending['needs_improvement'] == 0 and pending['completed'] == 0
    assert client.put(url, json={'version': 2, 'comment': '推导完整', 'status': 'completed'}).status_code == 200
    assert client.get('/api/teaching/stats').json()['completed'] == 1
    client.post(f'/api/assignments/{aid}/archive')
    assert client.get('/api/teaching/stats').json()['submitted'] == baseline['submitted']
    assert client.put(url, json={'version': 2, 'comment': 'new', 'status': 'completed'}).status_code == 409
    client.post('/api/auth/logout')
    login(client)
    final = next(a for a in client.get('/api/assignments').json() if a['id'] == aid)
    assert final['submission']['review']['status'] == 'completed' and len(final['submission']['review_history']) == 1


def test_other_teacher_and_other_student_are_isolated(client):
    from backend.app.platform.auth import hash_password
    login(client, 'teacher')
    qid = client.post('/api/questions', json={'title': 'private', 'topic': 'x', 'content': 'secret'}).json()['id']
    aid = client.post('/api/assignments', json={'class_id': 'demo-class', 'title': 'private', 'topic': 'x', 'content': 'x', 'due_date': date.today().isoformat()}).json()['id']
    login(client)
    client.put(f'/api/assignments/{aid}/submission', json={'answer': 'private student answer'})
    with SessionLocal() as db:
        for role in ('teacher', 'student'):
            db.add(User(id=f'{role}2', username=f'{role}2', role=role, name='同名测试', password_hash=hash_password('test-pass')))
        db.commit()
    assert client.post('/api/auth/login', json={'username': 'teacher2', 'password': 'test-pass', 'role': 'teacher'}).status_code == 200
    assert client.get('/api/questions').json() == [] and client.get('/api/assignments').json() == []
    for suffix in ('publish', 'archive', 'copy'):
        assert client.post(f'/api/assignments/{aid}/{suffix}').status_code == 404
    assert client.patch(f'/api/assignments/{aid}', json={'title': 'hack'}).status_code == 404
    assert client.delete(f'/api/assignments/{aid}').status_code == 404
    assert client.patch(f'/api/questions/{qid}', json={'title': 'hack'}).status_code == 404
    assert client.post(f'/api/questions/{qid}/archive').status_code == 404
    assert client.post('/api/assignments/drafts', json={'question_ids': [qid]}).status_code == 404
    assert client.put(f'/api/assignments/{aid}/submissions/student/review', json={'version': 1, 'comment': 'hack', 'status': 'completed'}).status_code == 404
    client.post('/api/auth/login', json={'username': 'student2', 'password': 'test-pass', 'role': 'student'})
    assert 'private student answer' not in client.get('/api/assignments').text
    assert client.get('/api/assignments').json() == []
    assert client.put(f'/api/assignments/{aid}/submission', json={'answer': 'cross-class'}).status_code == 404


def test_past_deadline_blocks_writes_and_validation(client):
    from backend.app.platform.database import Assignment
    login(client, 'teacher')
    aid = client.post('/api/assignments', json={'class_id': 'demo-class', 'title': 'expired', 'topic': 'x', 'content': 'x', 'due_date': date.today().isoformat()}).json()['id']
    with SessionLocal() as db:
        db.get(Assignment, aid).due_date = (date.today() - timedelta(days=1)).isoformat()
        db.commit()
    assert client.post('/api/assignments/drafts', json={'due_date': 'nonsense'}).status_code == 422
    assert client.post('/api/assignments/drafts', json={'title': None}).status_code == 422
    assert client.post('/api/questions', json={'title': '   ', 'topic': 'x', 'content': 'x'}).status_code == 422
    assert client.post('/api/assignments/drafts', json={'status': 'published'}).status_code == 422
    login(client)
    assert client.put(f'/api/assignments/{aid}/submission', json={'answer': 'late'}).status_code == 409


def test_concurrent_review_and_resubmit_preserves_version_boundary(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    login(client, 'teacher')
    aid = client.post('/api/assignments', json={'class_id': 'demo-class', 'title': 'race', 'topic': 'x', 'content': 'x', 'due_date': date.today().isoformat()}).json()['id']
    with TestClient(app, headers=HEADERS) as student_client:
        login(student_client)
        student_client.put(f'/api/assignments/{aid}/submission', json={'answer': 'v1'})
        barrier = Barrier(2)

        def review():
            barrier.wait()
            return client.put(f'/api/assignments/{aid}/submissions/student/review', json={'version': 1, 'comment': 'v1 feedback', 'status': 'completed'})

        def resubmit():
            barrier.wait()
            return student_client.put(f'/api/assignments/{aid}/submission', json={'answer': 'v2'})

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(review), pool.submit(resubmit)
            review_result, submit_result = a.result(), b.result()
        assert review_result.status_code in (200, 409)
        assert submit_result.status_code == 200
        final = next(a for a in student_client.get('/api/assignments').json() if a['id'] == aid)['submission']
        assert final['version'] == 2 and final['review'] is None
        assert all(r['version'] == 1 and r['answer_snapshot'] == 'v1' for r in final['review_history'])
        assert len(final['review_history']) == (1 if review_result.status_code == 200 else 0)
