"""Version 2 -> 3 persistence and failure tests using independently defined SQL."""
import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import create_engine, inspect

from migrations.restore import restore
from migrations.upgrade import upgrade


def version_two(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''
        CREATE TABLE users (id VARCHAR(40) PRIMARY KEY, username VARCHAR(80) UNIQUE, password_hash VARCHAR(200), role VARCHAR(20), name VARCHAR(80));
        CREATE TABLE sessions (token_hash VARCHAR(64) PRIMARY KEY, user_id VARCHAR(40), expires INTEGER);
        CREATE TABLE conversations (id VARCHAR(40) PRIMARY KEY, user_id VARCHAR(40), question TEXT, answer TEXT, topic VARCHAR(40), favorite BOOLEAN, created_at VARCHAR(40));
        CREATE TABLE assignments (id VARCHAR(40) PRIMARY KEY, teacher_id VARCHAR(40), title VARCHAR(100), content TEXT, topic VARCHAR(40), due_date VARCHAR(10), created_at VARCHAR(40), status VARCHAR(20) NOT NULL DEFAULT 'published');
        CREATE TABLE submissions (id VARCHAR(90) PRIMARY KEY, assignment_id VARCHAR(40), student_id VARCHAR(40), answer TEXT, created_at VARCHAR(40), version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE questions (id VARCHAR(40) PRIMARY KEY, teacher_id VARCHAR(40), title VARCHAR(100), topic VARCHAR(40), content TEXT, reference_answer TEXT, archived BOOLEAN, created_at VARCHAR(40), updated_at VARCHAR(40));
        CREATE TABLE reviews (id VARCHAR(40) PRIMARY KEY, submission_id VARCHAR(90), teacher_id VARCHAR(40), version INTEGER, comment TEXT, status VARCHAR(30), answer_snapshot TEXT, reviewed_at VARCHAR(40), UNIQUE(submission_id,version));
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at VARCHAR(40));
        INSERT INTO schema_migrations VALUES (2, '2026-09-18T10:00:00Z');
        INSERT INTO users VALUES
          ('teacher','teacher','legacy-teacher-hash','teacher','原教师'),
          ('t2','other_teacher','other-teacher-hash','teacher','另一原教师'),
          ('student','student','legacy-student-hash','student','原学生'),
          ('s2','other_student','other-student-hash','student','另一原学生');
        INSERT INTO sessions VALUES ('existing-session-digest','s2',1800000000);
        INSERT INTO conversations VALUES ('c','s2','私人原问题','原模型反馈','极限',1,'2026-09-18T10:00:00Z');
        INSERT INTO assignments VALUES
          ('published','teacher','已发布旧作业','题干 $x^2$','导数','2026-09-28','2026-09-18','published'),
          ('draft','teacher','','','极限','','2026-09-18','draft'),
          ('archived','t2','另一教师归档作业','原题干','极限','2026-09-18','2026-09-18','archived');
        INSERT INTO submissions VALUES
          ('published:s2','published','s2','第二版原作答','2026-09-18',2),
          ('archived:student','archived','student','归档前原作答','2026-09-18',1);
        INSERT INTO questions VALUES ('q','teacher','原题','导数','原题干','保密参考答案',0,'2026-09-18','2026-09-18');
        INSERT INTO reviews VALUES
          ('r1','published:s2','teacher',1,'旧版本评语','needs_improvement','第一版原作答','2026-09-18T10:00:00Z'),
          ('r2','published:s2','teacher',2,'新版评语','completed','第二版原作答','2026-09-18T11:00:00Z'),
          ('r3','archived:student','t2',1,'归档前评语','completed','归档前原作答','2026-09-18T11:00:00Z');
        ''')


def snapshot(path):
    with closing(sqlite3.connect(path)) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        return {name: db.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall() for (name,) in tables}


@pytest.fixture
def metadata():
    # Import after collection so this file cannot pre-empt another module's
    # explicitly configured test database merely by being listed first.
    from backend.app.platform.database import Base
    return Base.metadata


def test_v2_upgrade_preserves_accounts_versions_feedback_private_records_and_audience(tmp_path, metadata):
    path = tmp_path / 'old-v2.db'
    version_two(path)
    before = snapshot(path)
    engine = create_engine(f'sqlite:///{path}')
    try:
        backup = upgrade(engine, metadata)
        assert backup and backup.exists() and '.before-v3-' in backup.name
        after = snapshot(path)
        for table, rows in before.items():
            if table == 'schema_migrations':
                assert rows[0] in after[table]
            else:
                assert [row[:len(rows[0])] for row in after[table]] == rows, table
        assert [row[0] for row in after['schema_migrations']] == [2, 3]
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            classes = db.execute('SELECT id,teacher_id,name FROM classrooms ORDER BY teacher_id').fetchall()
            assert len(classes) == 2 and {row[1] for row in classes} == {'teacher', 't2'}
            assert all(row[2] == '历史教学班' for row in classes)
            for class_id, teacher_id, _ in classes:
                assert {row[0] for row in db.execute('SELECT student_id FROM class_members WHERE class_id=? AND active=1', (class_id,))} == {'student', 's2'}
                assert db.execute('SELECT COUNT(*) FROM assignments WHERE teacher_id=? AND class_id IS NULL', (teacher_id,)).fetchone()[0] == 0
                assert db.execute('SELECT COUNT(*) FROM assignments WHERE teacher_id=? AND class_id!=?', (teacher_id, class_id)).fetchone()[0] == 0
            audience = set(db.execute('SELECT assignment_id,student_id FROM assignment_recipients'))
            assert audience == {('published', 'student'), ('published', 's2'), ('archived', 'student'), ('archived', 's2')}
            assert {row[0] for row in db.execute('SELECT id FROM users WHERE is_demo=1')} == {'teacher', 'student'}
            # Ambiguous historic ownership must not be assigned arbitrarily.
            assert db.execute('SELECT COUNT(*) FROM users WHERE created_by IS NOT NULL').fetchone()[0] == 0
        assert upgrade(engine, metadata) is None
        assert snapshot(path) == after
        restored = tmp_path / 'restored-v2.db'
        restore(backup, restored)
        assert snapshot(restored) == before
        with pytest.raises(ValueError, match='already exists'):
            restore(backup, restored)
    finally:
        engine.dispose()


def test_v3_failed_upgrade_rolls_back_every_new_column_and_preserves_v2_backup(tmp_path, metadata):
    path = tmp_path / 'failure-v2.db'
    version_two(path)
    before = snapshot(path)
    engine = create_engine(f'sqlite:///{path}')

    class FailingMetadata:
        def create_all(self, connection):
            connection.exec_driver_sql('CREATE TABLE must_rollback (id INTEGER)')
            raise RuntimeError('v3 intentional failure')

    try:
        with pytest.raises(RuntimeError, match='v3 intentional failure'):
            upgrade(engine, FailingMetadata())
        assert snapshot(path) == before
        assert 'active' not in {column['name'] for column in inspect(engine).get_columns('users')}
        assert 'class_id' not in {column['name'] for column in inspect(engine).get_columns('assignments')}
        backups = list(tmp_path.glob('failure-v2.before-v3-*.db'))
        assert len(backups) == 1 and snapshot(backups[0]) == before
        upgrade(engine, metadata)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0] == 3
    finally:
        engine.dispose()


def test_new_v3_database_is_empty_and_incomplete_or_newer_schema_is_rejected(tmp_path, metadata):
    path = tmp_path / 'fresh.db'
    engine = create_engine(f'sqlite:///{path}')
    try:
        assert upgrade(engine, metadata) is None
        with engine.begin() as connection:
            assert connection.exec_driver_sql('SELECT COUNT(*) FROM users').scalar() == 0
            assert connection.exec_driver_sql('SELECT COUNT(*) FROM classrooms').scalar() == 0
            connection.exec_driver_sql('DROP TABLE assignment_recipients')
        with pytest.raises(RuntimeError, match='Incomplete schema'):
            upgrade(engine, metadata)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO schema_migrations VALUES (99, 'future')")
        with pytest.raises(RuntimeError, match='newer than'):
            upgrade(engine, metadata)
    finally:
        engine.dispose()


def test_single_teacher_legacy_students_become_managed_without_new_accounts(tmp_path, metadata):
    path = tmp_path / 'single-teacher-v2.db'
    version_two(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("DELETE FROM users WHERE id='t2'")
        db.execute("DELETE FROM assignments WHERE teacher_id='t2'")
        db.execute("DELETE FROM submissions WHERE assignment_id='archived'")
        db.execute("DELETE FROM reviews WHERE teacher_id='t2'")
        db.commit()
    engine = create_engine(f'sqlite:///{path}')
    try:
        upgrade(engine, metadata)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 3
            assert db.execute("SELECT COUNT(*) FROM users WHERE role='student' AND created_by='teacher'").fetchone()[0] == 2
            assert db.execute('SELECT COUNT(*) FROM classrooms').fetchone()[0] == 1
    finally:
        engine.dispose()


def test_multi_teacher_migrated_members_are_readable_but_accounts_remain_unmanaged(tmp_path, metadata, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from backend.app import main
    from backend.app.platform import database
    from backend.app.platform.auth import hash_password

    path = tmp_path / 'multi-teacher-http-v2.db'
    version_two(path)
    password = 'MigrationTest123!'
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE users SET password_hash=? WHERE role='teacher'", (hash_password(password),))
        db.commit()
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setenv('SHUBAN_SEED_DEMO', 'false')
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'SessionLocal', sessions)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'SessionLocal', sessions)

    def isolated_db():
        with sessions() as db:
            yield db

    original_overrides = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[database.get_db] = isolated_db
    clients = []
    try:
        upgrade(engine, metadata)
        for username in ('teacher', 'other_teacher'):
            client = TestClient(main.app, headers={'X-Requested-With': 'shuban-web'})
            clients.append(client)
            logged_in = client.post('/api/auth/login', json={
                'username': username, 'password': password, 'role': 'teacher'})
            assert logged_in.status_code == 200, logged_in.text
            classes_response = client.get('/api/classes')
            assert classes_response.status_code == 200
            classrooms = classes_response.json()
            assert len(classrooms) == 1
            class_id = classrooms[0]['id']
            roster = client.get(f'/api/classes/{class_id}/students')
            assert roster.status_code == 200
            students = roster.json()
            assert {student['id'] for student in students} == {'student', 's2'}
            assert all(student['manageable'] is False for student in students)
            for student in students:
                student_id = student['id']
                assert client.post(f'/api/students/{student_id}/password', json={
                    'password': 'Replacement123!'}).status_code == 404
                assert client.patch(f'/api/students/{student_id}', json={'active': False}).status_code == 404
                assert client.patch(f'/api/students/{student_id}', json={'name': 'Not permitted'}).status_code == 404
            # Historical account ownership is unknown; class membership is still
            # owned by each class teacher and can be maintained independently.
            response = client.patch(f'/api/classes/{class_id}/members/s2', json={'active': False})
            assert response.status_code == 200 and response.json()['manageable'] is False
            assert response.json()['member_active'] is False
            response = client.patch(f'/api/classes/{class_id}/members/s2', json={'active': True})
            assert response.status_code == 200 and response.json()['member_active'] is True
        with closing(sqlite3.connect(path)) as db:
            assert db.execute("SELECT COUNT(*) FROM users WHERE role='student' AND active=1 AND created_by IS NULL").fetchone()[0] == 2
            assert db.execute("SELECT id,password_hash FROM users WHERE role='student' ORDER BY id").fetchall() == [
                ('s2', 'other-student-hash'), ('student', 'legacy-student-hash')]
    finally:
        for client in clients:
            client.close()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)
        engine.dispose()
