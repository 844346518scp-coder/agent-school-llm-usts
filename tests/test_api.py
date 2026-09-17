"""Authentication, role boundaries, persistence, and the real assignment loop."""
import os
from datetime import date, timedelta
from pathlib import Path
import tempfile

# A disposable database outside the project; never touch demo.db.
_test_db = tempfile.TemporaryDirectory(prefix='shuban-tests-')
os.environ['DATABASE_URL'] = f'sqlite:///{Path(_test_db.name) / "test.db"}'

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.platform.database import Base, engine, SessionLocal, User, Session, Conversation
from backend.app.platform.auth import token_hash

HEADERS = {'X-Requested-With': 'shuban-web'}


@pytest.fixture(scope='session', autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    _test_db.cleanup()


@pytest.fixture(autouse=True)
def database():
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
    response = client.post('/api/assignments', json={'title': '测试作业', 'content': '解释导数', 'topic': '导数与微分', 'due_date': (date.today() + timedelta(days=1)).isoformat()})
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
