"""HTTP acceptance for real teacher workspaces, using a fresh private DB per test.

The fixture overrides the application's DB dependency and startup globals. It never
initializes the caller's configured database, even when this module runs alone.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


HEADERS = {'X-Requested-With': 'shuban-web'}
PASSWORD = 'TestPassword123!'
CHANGED_PASSWORD = 'ChangedPassword456!'


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from backend.app import main
    from backend.app.platform import database

    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setenv('SHUBAN_SEED_DEMO', 'false')
    engine = create_engine(f'sqlite:///{tmp_path / "workspace.db"}',
                           connect_args={'check_same_thread': False, 'timeout': 15})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'SessionLocal', sessions)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'SessionLocal', sessions)

    def get_db():
        with sessions() as db:
            yield db

    previous = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[database.get_db] = get_db
    clients = []

    def client():
        created = TestClient(main.app, headers=HEADERS)
        clients.append(created)
        return created

    try:
        main.initialize_database()
        yield SimpleNamespace(client=client, sessions=sessions, engine=engine,
                              restart=main.initialize_database)
    finally:
        for created in clients:
            created.close()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
        engine.dispose()


def success(response):
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_teacher(workspace, username='teacher_one', creator=None):
    client = workspace.client()
    fields = {'username': username, 'name': username, 'password': PASSWORD}
    if creator is None:
        user = success(client.post('/api/auth/setup', json=fields))
    else:
        user = success(creator.post('/api/auth/teachers', json=fields))
        success(client.post('/api/auth/login', json={
            'username': username, 'password': PASSWORD, 'role': 'teacher'}))
        # New teachers may receive the same first-use password gate as students.
        if user.get('must_change_password'):
            success(client.post('/api/auth/password', json={
                'current_password': PASSWORD, 'new_password': CHANGED_PASSWORD}))
    return client, user


def create_class(teacher, name='高数一班'):
    return success(teacher.post('/api/classes', json={
        'name': name, 'course': '高等数学', 'term': '2026 秋季'}))


def create_student(workspace, teacher, classroom, username='student_one', change=True):
    user = success(teacher.post(f'/api/classes/{classroom["id"]}/students', json={
        'username': username, 'name': username, 'password': PASSWORD}))
    client = workspace.client()
    success(client.post('/api/auth/login', json={
        'username': username, 'password': PASSWORD, 'role': 'student'}))
    if change:
        success(client.post('/api/auth/password', json={
            'current_password': PASSWORD, 'new_password': CHANGED_PASSWORD}))
    return client, user


def publish(teacher, classroom, title='极限练习'):
    return success(teacher.post('/api/assignments', json={
        'title': title, 'topic': '函数与极限', 'content': '解释极限的含义。',
        'due_date': (date.today() + timedelta(days=2)).isoformat(),
        'class_id': classroom['id']}))


def assignment_ids(client):
    return {item['id'] for item in success(client.get('/api/assignments'))}


def test_first_setup_has_no_seed_and_restarts_do_not_recreate_demo(workspace):
    from backend.app.platform.database import Assignment, User

    client = workspace.client()
    assert success(client.get('/api/auth/setup')) == {'required': True}
    assert client.post('/api/auth/setup', headers={'X-Requested-With': ''}, json={
        'username': 'first', 'name': '教师', 'password': PASSWORD}).status_code == 403
    assert client.post('/api/auth/setup', json={
        'username': 'first', 'name': '教师', 'password': 'weak'}).status_code == 422
    with workspace.sessions() as db:
        assert list(db.scalars(select(User))) == []
        assert list(db.scalars(select(Assignment))) == []
    teacher, user = create_teacher(workspace)
    assert user['role'] == 'teacher' and user['is_demo'] is False
    assert user['active'] is True and user['must_change_password'] is False
    assert 'password' not in user and 'password_hash' not in user
    assert success(teacher.get('/api/auth/me'))['id'] == user['id']
    assert success(client.get('/api/auth/setup')) == {'required': False}
    assert client.post('/api/auth/setup', json={
        'username': 'second', 'name': '第二位', 'password': PASSWORD}).status_code == 409
    workspace.restart()
    workspace.restart()
    with workspace.sessions() as db:
        users = list(db.scalars(select(User)))
        assert [item.id for item in users] == [user['id']]
        assert users[0].password_hash != PASSWORD
        assert list(db.scalars(select(Assignment))) == []
    for role in ('teacher', 'student'):
        assert client.post('/api/auth/login', json={
            'username': role, 'password': f'{role.title()}123!', 'role': role}).status_code == 401


def test_simultaneous_setup_creates_exactly_one_teacher(workspace):
    from backend.app.platform.database import User

    clients = [workspace.client(), workspace.client()]
    barrier = Barrier(2)

    def setup(index):
        barrier.wait()
        return clients[index].post('/api/auth/setup', json={
            'username': f'first_{index}', 'name': f'教师{index}', 'password': PASSWORD})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(setup, range(2)))
    assert sum(response.status_code in (200, 201) for response in responses) == 1
    assert sum(response.status_code == 409 for response in responses) == 1
    with workspace.sessions() as db:
        assert len(list(db.scalars(select(User)))) == 1


def test_profile_and_teacher_creation_keep_creator_session(workspace):
    first, user = create_teacher(workspace)
    second, other = create_teacher(workspace, 'teacher_two', first)
    assert other['must_change_password'] is True
    assert success(first.get('/api/auth/me'))['id'] == user['id']
    assert success(second.get('/api/auth/me'))['id'] == other['id']
    assert success(first.patch('/api/auth/profile', json={'name': '新姓名'}))['name'] == '新姓名'
    assert first.patch('/api/auth/profile', json={'name': '   '}).status_code == 422
    assert first.patch('/api/auth/profile', json={'role': 'student'}).status_code == 422
    assert first.post('/api/auth/teachers', json={
        'username': 'teacher_two', 'name': '重复', 'password': PASSWORD}).status_code == 409
    anonymous = workspace.client()
    assert anonymous.post('/api/auth/teachers', json={
        'username': 'unauthorized', 'name': '匿名', 'password': PASSWORD}).status_code == 401


def test_temporary_password_gate_then_password_rotation_revokes_every_old_session(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student, user = create_student(workspace, teacher, classroom, change=False)
    assert success(student.get('/api/auth/me'))['must_change_password'] is True
    for method, path, body in (
        ('get', '/api/assignments', None), ('get', '/api/conversations', None),
        ('post', '/api/conversations', {'question': '什么是极限？'}),
        ('patch', '/api/auth/profile', {'name': '未改密用户'}),
        ('post', '/api/agent/ask', {'question': '什么是极限？', 'role': 'student'}),
    ):
        response = getattr(student, method)(path, **({'json': body} if body else {}))
        assert response.status_code == 403, (path, response.text)
    second_session = workspace.client()
    success(second_session.post('/api/auth/login', json={
        'username': user['username'], 'password': PASSWORD, 'role': 'student'}))
    assert student.post('/api/auth/password', json={
        'current_password': 'wrong', 'new_password': CHANGED_PASSWORD}).status_code == 403
    for new_password in ('1234567890', 'abcdefghij', 'Short12!'):
        assert student.post('/api/auth/password', json={
            'current_password': PASSWORD, 'new_password': new_password}).status_code == 422
    old_cookie = student.cookies.get('shuxue_session')
    changed = success(student.post('/api/auth/password', json={
        'current_password': PASSWORD, 'new_password': CHANGED_PASSWORD}))
    assert changed['must_change_password'] is False
    assert student.cookies.get('shuxue_session') != old_cookie
    assert second_session.get('/api/auth/me').status_code == 401
    assert success(student.get('/api/assignments')) == []
    assert second_session.post('/api/auth/login', json={
        'username': user['username'], 'password': PASSWORD, 'role': 'student'}).status_code == 401


def test_student_reset_disable_and_reenable_are_owner_only_and_revoke_sessions(workspace):
    teacher, _ = create_teacher(workspace)
    other, _ = create_teacher(workspace, 'teacher_two', teacher)
    classroom = create_class(teacher)
    student, user = create_student(workspace, teacher, classroom)
    sid = user['id']
    for action, path, payload in (
        ('patch', f'/api/students/{sid}', {'name': '窃改'}),
        ('patch', f'/api/students/{sid}', {'active': False}),
        ('post', f'/api/students/{sid}/password', {'password': PASSWORD}),
    ):
        assert getattr(other, action)(path, json=payload).status_code == 404
    success(teacher.post(f'/api/students/{sid}/password', json={'password': PASSWORD}))
    assert student.get('/api/auth/me').status_code == 401
    assert student.post('/api/auth/login', json={
        'username': user['username'], 'password': CHANGED_PASSWORD, 'role': 'student'}).status_code == 401
    assert success(student.post('/api/auth/login', json={
        'username': user['username'], 'password': PASSWORD, 'role': 'student'}))['must_change_password']
    success(student.post('/api/auth/password', json={
        'current_password': PASSWORD, 'new_password': CHANGED_PASSWORD}))
    success(teacher.patch(f'/api/students/{sid}', json={'active': False}))
    assert student.get('/api/auth/me').status_code == 401
    assert student.post('/api/auth/login', json={
        'username': user['username'], 'password': CHANGED_PASSWORD, 'role': 'student'}).status_code == 401
    success(teacher.patch(f'/api/students/{sid}', json={'active': True, 'name': '真实学生'}))
    assert success(student.post('/api/auth/login', json={
        'username': user['username'], 'password': CHANGED_PASSWORD, 'role': 'student'}))['name'] == '真实学生'
    assert student.patch(f'/api/students/{sid}', json={'active': False}).status_code == 403


def test_two_teachers_classes_members_assignments_questions_and_filters_are_isolated(workspace):
    first, _ = create_teacher(workspace)
    second, _ = create_teacher(workspace, 'teacher_two', first)
    class_one, class_two = create_class(first), create_class(second, '高数二班')
    student_one, user_one = create_student(workspace, first, class_one)
    student_two, _ = create_student(workspace, second, class_two, 'student_two')
    assignment = publish(first, class_one)
    q = success(first.post('/api/questions', json={
        'title': '私有题', 'topic': '极限', 'content': '题干', 'reference_answer': 'PRIVATE SOLUTION'}))
    assert [item['id'] for item in success(first.get('/api/classes'))] == [class_one['id']]
    assert [item['id'] for item in success(second.get('/api/classes'))] == [class_two['id']]
    assert success(second.get('/api/assignments')) == []
    assert success(second.get('/api/questions')) == []
    for path in (f'/api/classes/{class_one["id"]}/students',
                 f'/api/assignments?class_id={class_one["id"]}',
                 f'/api/teaching/stats?class_id={class_one["id"]}'):
        assert second.get(path).status_code == 404, path
    for method, path, body in (
        ('patch', f'/api/classes/{class_one["id"]}', {'name': '窃改'}),
        ('post', f'/api/classes/{class_one["id"]}/students', {'username': 'bad', 'name': 'bad', 'password': PASSWORD}),
        ('patch', f'/api/classes/{class_one["id"]}/members/{user_one["id"]}', {'active': False}),
        ('post', f'/api/classes/{class_two["id"]}/members', {'username': user_one['username']}),
        ('patch', f'/api/questions/{q["id"]}', {'title': '窃改'}),
        ('post', '/api/assignments/drafts', {'class_id': class_one['id']}),
        ('post', f'/api/assignments/{assignment["id"]}/copy', {}),
        ('post', f'/api/assignments/{assignment["id"]}/archive', {}),
    ):
        assert getattr(second, method)(path, json=body).status_code == 404, path
    assert assignment['id'] in assignment_ids(student_one)
    assert assignment['id'] not in assignment_ids(student_two)
    assert student_two.put(f'/api/assignments/{assignment["id"]}/submission', json={'answer': '窃交'}).status_code == 404
    assert 'PRIVATE SOLUTION' not in student_one.get('/api/assignments').text
    for path in ('/api/classes', f'/api/classes/{class_one["id"]}/students', '/api/teaching/stats'):
        assert student_one.get(path).status_code == 403
    assert student_one.post('/api/auth/teachers', json={
        'username': 'notteacher', 'name': '越权', 'password': PASSWORD}).status_code == 403


def test_publish_requires_class_and_active_recipients_and_rejects_class_change(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    draft = success(teacher.post('/api/assignments/drafts', json={
        'title': '待发布', 'topic': '极限', 'content': '完整题干',
        'due_date': date.today().isoformat()}))
    path = f'/api/assignments/{draft["id"]}'
    assert teacher.post(path + '/publish').status_code == 422
    success(teacher.patch(path, json={'class_id': classroom['id']}))
    assert teacher.post(path + '/publish').status_code == 422
    _, user = create_student(workspace, teacher, classroom)
    success(teacher.patch(f'/api/students/{user["id"]}', json={'active': False}))
    assert teacher.post(path + '/publish').status_code == 422
    success(teacher.patch(f'/api/students/{user["id"]}', json={'active': True}))
    published = success(teacher.post(path + '/publish'))
    assert published['recipient_count'] == 1 and published['class_name'] == classroom['name']
    other_class = create_class(teacher, '另一班')
    assert teacher.patch(path, json={'class_id': other_class['id']}).status_code == 409
    success(teacher.patch(f'/api/classes/{other_class["id"]}', json={'archived': True}))
    assert teacher.post('/api/assignments', json={
        'title': '归档班作业', 'topic': '极限', 'content': 'x', 'due_date': date.today().isoformat(),
        'class_id': other_class['id']}).status_code == 409


def test_recipient_snapshot_does_not_expand_on_join_or_repeat_publish(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student_one, _ = create_student(workspace, teacher, classroom)
    assignment = publish(teacher, classroom)
    student_two, _ = create_student(workspace, teacher, classroom, 'student_two')
    repeated = success(teacher.post(f'/api/assignments/{assignment["id"]}/publish'))
    assert repeated['recipient_count'] == 1
    assert assignment['id'] not in assignment_ids(student_two)
    assert student_two.put(f'/api/assignments/{assignment["id"]}/submission', json={'answer': '迟加入'}).status_code == 404
    copied = success(teacher.post(f'/api/assignments/{assignment["id"]}/copy'))
    assert copied['class_id'] == classroom['id'] and copied['submissions'] == []
    success(teacher.patch(f'/api/assignments/{copied["id"]}', json={'due_date': date.today().isoformat()}))
    newest = success(teacher.post(f'/api/assignments/{copied["id"]}/publish'))
    assert newest['recipient_count'] == 2
    assert newest['id'] in assignment_ids(student_one) & assignment_ids(student_two)


def test_removed_members_keep_history_but_cannot_submit_and_new_assignments_exclude_them(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student_one, user_one = create_student(workspace, teacher, classroom)
    create_student(workspace, teacher, classroom, 'student_two')
    original = publish(teacher, classroom)
    url = f'/api/assignments/{original["id"]}/submission'
    success(student_one.put(url, json={'answer': '原始作答'}))
    member_path = f'/api/classes/{classroom["id"]}/members/{user_one["id"]}'
    success(teacher.patch(member_path, json={'active': False}))
    assert original['id'] in assignment_ids(student_one)
    assert next(item for item in success(student_one.get('/api/assignments'))
                if item['id'] == original['id'])['can_submit'] is False
    assert student_one.put(url, json={'answer': '退班后修改'}).status_code == 409
    later = publish(teacher, classroom, '退班后发布')
    assert later['recipient_count'] == 1 and later['id'] not in assignment_ids(student_one)
    success(teacher.patch(member_path, json={'active': True}))
    assert later['id'] not in assignment_ids(student_one)
    success(student_one.put(url, json={'answer': '恢复成员后修改'}))
    assert next(item for item in success(student_one.get('/api/assignments'))
                if item['id'] == original['id'])['can_submit'] is True
    rows = success(teacher.get(f'/api/classes/{classroom["id"]}/students'))
    assert next(row for row in rows if row['id'] == user_one['id'])['member_active'] is True
    another = create_class(teacher, '共享学生的班级')
    success(teacher.post(f'/api/classes/{another["id"]}/members', json={'username': user_one['username']}))
    assert success(teacher.get(f'/api/classes/{another["id"]}/students'))[0]['id'] == user_one['id']


def test_class_archive_makes_submission_feedback_and_due_date_read_only_until_restore(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student, user = create_student(workspace, teacher, classroom)
    assignment = publish(teacher, classroom)
    base = f'/api/assignments/{assignment["id"]}'
    success(student.put(base + '/submission', json={'answer': '保留作答'}))
    review = {'version': 1, 'comment': '有依据', 'status': 'completed'}
    review_path = f'{base}/submissions/{user["id"]}/review'
    success(teacher.put(review_path, json=review))
    success(teacher.patch(f'/api/classes/{classroom["id"]}', json={'archived': True}))
    assert assignment['id'] in assignment_ids(student)
    archived_view = next(item for item in success(student.get('/api/assignments'))
                         if item['id'] == assignment['id'])
    assert archived_view['class_archived'] is True and archived_view['can_submit'] is False
    assert student.put(base + '/submission', json={'answer': '归档后修改'}).status_code == 409
    assert teacher.put(review_path, json=review).status_code == 409
    assert teacher.patch(base, json={'due_date': (date.today() + timedelta(days=3)).isoformat()}).status_code == 409
    stats = success(teacher.get('/api/teaching/stats'))
    assert stats['published'] == stats['expected'] == stats['submitted'] == 0
    discarded_copy = success(teacher.post(base + '/copy'))
    assert discarded_copy['class_id'] is None and discarded_copy['status'] == 'draft'
    success(teacher.delete(f'/api/assignments/{discarded_copy["id"]}'))
    copied = success(teacher.post(base + '/copy'))
    assert copied['class_id'] is None and copied['submissions'] == []
    other_class = create_class(teacher, '用于新学期的班级')
    success(teacher.post(f'/api/classes/{other_class["id"]}/members', json={'username': user['username']}))
    success(teacher.patch(f'/api/assignments/{copied["id"]}', json={
        'title': '新学期作业', 'class_id': other_class['id'], 'due_date': date.today().isoformat()}))
    success(teacher.post(f'/api/assignments/{copied["id"]}/publish'))
    # A copied assignment must not revive or move the archived original.
    original = next(item for item in success(teacher.get('/api/assignments')) if item['id'] == assignment['id'])
    assert original['class_id'] == classroom['id'] and original['class_archived'] is True
    success(teacher.patch(f'/api/classes/{classroom["id"]}', json={'archived': False}))
    assert success(teacher.get('/api/teaching/stats'))['completed'] == 1
    success(student.put(base + '/submission', json={'answer': '恢复后第二版'}))
    assert teacher.put(review_path, json=review).status_code == 409
    success(teacher.post(base + '/archive'))
    assert student.put(base + '/submission', json={'answer': '作业归档后修改'}).status_code == 409


def test_stats_are_real_class_scoped_counts_and_review_changes_follow_versions(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student_one, user_one = create_student(workspace, teacher, classroom)
    student_two, user_two = create_student(workspace, teacher, classroom, 'student_two')
    other_class = create_class(teacher, '无作业班级')
    create_student(workspace, teacher, other_class, 'student_three')
    assignment = publish(teacher, classroom)
    base = f'/api/assignments/{assignment["id"]}'
    initial = success(teacher.get('/api/teaching/stats'))
    assert {key: initial[key] for key in ('classes', 'students', 'published', 'expected', 'unsubmitted', 'submitted')} == {
        'classes': 2, 'students': 3, 'published': 1, 'expected': 2, 'unsubmitted': 2, 'submitted': 0}
    success(student_one.put(base + '/submission', json={'answer': '第一人'}))
    success(student_two.put(base + '/submission', json={'answer': '第二人'}))
    success(teacher.put(f'{base}/submissions/{user_one["id"]}/review', json={
        'version': 1, 'comment': '完整', 'status': 'completed'}))
    success(teacher.put(f'{base}/submissions/{user_two["id"]}/review', json={
        'version': 1, 'comment': '继续补充', 'status': 'needs_improvement'}))
    stats = success(teacher.get('/api/teaching/stats', params={'class_id': classroom['id']}))
    assert {key: stats[key] for key in ('students', 'expected', 'submitted', 'unsubmitted', 'completed', 'needs_improvement', 'pending')} == {
        'students': 2, 'expected': 2, 'submitted': 2, 'unsubmitted': 0, 'completed': 1, 'needs_improvement': 1, 'pending': 0}
    unrelated = success(teacher.get('/api/teaching/stats', params={'class_id': other_class['id']}))
    assert unrelated['students'] == 1 and unrelated['submitted'] == unrelated['expected'] == 0
    rows = {item['id']: item for item in success(teacher.get(f'/api/classes/{classroom["id"]}/students'))}
    assert rows[user_one['id']]['expected'] == rows[user_one['id']]['completed'] == 1
    assert rows[user_two['id']]['needs_improvement'] == 1
    success(student_two.put(base + '/submission', json={'answer': '第二人修订'}))
    stats = success(teacher.get('/api/teaching/stats'))
    assert stats['needs_improvement'] == 0 and stats['pending'] == 1 and stats['completed'] == 1
    success(student_one.post('/api/conversations', json={'question': 'PRIVATE STUDENT QUESTION'}))
    assert success(teacher.get('/api/conversations')) == []
    assert 'PRIVATE STUDENT QUESTION' not in teacher.get(f'/api/classes/{classroom["id"]}/students').text
    # One account in two classes contributes one active student to the overview.
    success(teacher.post(f'/api/classes/{other_class["id"]}/members', json={'username': user_one['username']}))
    assert success(teacher.get('/api/teaching/stats'))['students'] == 3
    success(teacher.patch(f'/api/classes/{classroom["id"]}/members/{user_one["id"]}', json={'active': False}))
    after_removal = success(teacher.get('/api/teaching/stats', params={'class_id': classroom['id']}))
    assert {key: after_removal[key] for key in ('students', 'expected', 'submitted', 'unsubmitted', 'completed', 'pending')} == {
        'students': 1, 'expected': 2, 'submitted': 2, 'unsubmitted': 0, 'completed': 1, 'pending': 1}
    success(teacher.patch(f'/api/students/{user_two["id"]}', json={'active': False}))
    after_disable = success(teacher.get('/api/teaching/stats', params={'class_id': classroom['id']}))
    assert {key: after_disable[key] for key in ('students', 'expected', 'submitted', 'unsubmitted', 'completed', 'pending')} == {
        'students': 0, 'expected': 2, 'submitted': 2, 'unsubmitted': 0, 'completed': 1, 'pending': 1}
    assert success(teacher.get('/api/teaching/stats'))['students'] == 2
    historical_rows = {item['id']: item for item in success(teacher.get(f'/api/classes/{classroom["id"]}/students'))}
    assert historical_rows[user_one['id']]['member_active'] is False
    assert historical_rows[user_two['id']]['active'] is False
    assert historical_rows[user_one['id']]['expected'] == historical_rows[user_two['id']]['expected'] == 1


@pytest.mark.parametrize('payload', [
    {'name': '   ', 'course': '高数', 'term': '2026'},
    {'name': 'x', 'course': '高数', 'term': '2026', 'teacher_id': 'spoof'},
])
def test_class_validation_rejects_blank_names_and_owner_spoofing(workspace, payload):
    teacher, _ = create_teacher(workspace)
    assert teacher.post('/api/classes', json=payload).status_code == 422


def test_student_creation_is_atomic_and_archived_class_disallows_membership_changes(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    _, user = create_student(workspace, teacher, classroom)
    other_class = create_class(teacher, '接收班')
    assert teacher.post(f'/api/classes/{other_class["id"]}/students', json={
        'username': user['username'], 'name': '重复账号', 'password': PASSWORD}).status_code == 409
    assert success(teacher.get(f'/api/classes/{other_class["id"]}/students')) == []
    for _ in range(2):
        success(teacher.post(f'/api/classes/{other_class["id"]}/members', json={'username': user['username']}))
    assert len(success(teacher.get(f'/api/classes/{other_class["id"]}/students'))) == 1
    success(teacher.patch(f'/api/classes/{other_class["id"]}', json={'archived': True}))
    for method, path, payload in (
        ('post', f'/api/classes/{other_class["id"]}/students', {'username': 'new_student', 'name': '新成员', 'password': PASSWORD}),
        ('post', f'/api/classes/{other_class["id"]}/members', {'username': user['username']}),
        ('patch', f'/api/classes/{other_class["id"]}/members/{user["id"]}', {'active': False}),
    ):
        assert getattr(teacher, method)(path, json=payload).status_code == 409
    assert teacher.post(f'/api/classes/{classroom["id"]}/members', json={'username': 'new_student'}).status_code == 404


def test_class_archive_and_submission_race_leave_consistent_read_only_history(workspace):
    teacher, _ = create_teacher(workspace)
    classroom = create_class(teacher)
    student, _ = create_student(workspace, teacher, classroom)
    assignment = publish(teacher, classroom)
    submission_path = f'/api/assignments/{assignment["id"]}/submission'
    success(student.put(submission_path, json={'answer': '归档竞态前'}))
    barrier = Barrier(2)

    def archive_class():
        barrier.wait()
        return teacher.patch(f'/api/classes/{classroom["id"]}', json={'archived': True})

    def submit():
        barrier.wait()
        return student.put(submission_path, json={'answer': '竞态中的第二版'})

    with ThreadPoolExecutor(max_workers=2) as pool:
        archived, submitted = pool.submit(archive_class), pool.submit(submit)
        archived_response, submitted_response = archived.result(), submitted.result()
    assert archived_response.status_code == 200
    assert submitted_response.status_code in (200, 409)
    result = next(item for item in success(student.get('/api/assignments')) if item['id'] == assignment['id'])
    assert result['class_archived'] is True and result['can_submit'] is False
    if submitted_response.status_code == 200:
        assert result['answer'] == '竞态中的第二版' and result['submission']['version'] == 2
    else:
        assert result['answer'] == '归档竞态前' and result['submission']['version'] == 1
    assert student.put(submission_path, json={'answer': '归档后禁止'}).status_code == 409
