import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import create_engine, inspect

from backend.app.platform.database import Base
from migrations.upgrade import upgrade
from migrations.restore import restore


def legacy(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''
        CREATE TABLE users (id VARCHAR(40) PRIMARY KEY, username VARCHAR(80) UNIQUE, password_hash VARCHAR(200), role VARCHAR(20), name VARCHAR(80));
        CREATE TABLE sessions (token_hash VARCHAR(64) PRIMARY KEY, user_id VARCHAR(40), expires INTEGER);
        CREATE TABLE conversations (id VARCHAR(40) PRIMARY KEY, user_id VARCHAR(40), question TEXT, answer TEXT, topic VARCHAR(40), favorite BOOLEAN, created_at VARCHAR(40));
        CREATE TABLE assignments (id VARCHAR(40) PRIMARY KEY, teacher_id VARCHAR(40), title VARCHAR(100), content TEXT, topic VARCHAR(40), due_date VARCHAR(10), created_at VARCHAR(40));
        CREATE TABLE submissions (id VARCHAR(90) PRIMARY KEY, assignment_id VARCHAR(40), student_id VARCHAR(40), answer TEXT, created_at VARCHAR(40));
        INSERT INTO users VALUES ('s','student','test-hash','student','演示学生'), ('t','teacher','test-hash','teacher','演示教师');
        INSERT INTO sessions VALUES ('test-digest','s',1);
        INSERT INTO conversations VALUES ('c','s','原问题','原反馈','极限',1,'2026-09-17');
        INSERT INTO assignments VALUES ('a','t','原作业','原题干','导数','2026-09-17','2026-09-17');
        INSERT INTO submissions VALUES ('a:s','a','s','原作答','2026-09-17');
        ''')


def test_upgrade_preserves_all_old_fields_and_restorable_backup(tmp_path):
    path = tmp_path / 'legacy.db'
    legacy(path)
    with closing(sqlite3.connect(path)) as db:
        before = {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in ('users', 'sessions', 'conversations', 'assignments', 'submissions')}
    engine = create_engine(f'sqlite:///{path}')
    try:
        backup = upgrade(engine, Base.metadata)
        assert backup.exists()
        with closing(sqlite3.connect(path)) as db:
            for table, records in before.items():
                after = db.execute(f'SELECT * FROM {table}').fetchall()
                assert [row[:len(records[0])] for row in after] == records
            assert db.execute('SELECT status FROM assignments').fetchone()[0] == 'published'
            assert db.execute('SELECT version FROM submissions').fetchone()[0] == 1
            assert db.execute('SELECT version FROM schema_migrations').fetchone()[0] == 2
        assert upgrade(engine, Base.metadata) is None
        restored = tmp_path / 'restored.db'
        restore(backup, restored)
        with closing(sqlite3.connect(restored)) as target:
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            for table, records in before.items():
                assert target.execute(f'SELECT * FROM {table}').fetchall() == records
        with pytest.raises(ValueError, match='already exists'):
            restore(backup, restored)
    finally:
        engine.dispose()


def test_migration_failure_rolls_back_ddl_and_retains_backup(tmp_path):
    path = tmp_path / 'failure.db'
    legacy(path)
    engine = create_engine(f'sqlite:///{path}')

    class FailingMetadata:
        def create_all(self, conn):
            raise RuntimeError('injected failure')

    try:
        with pytest.raises(RuntimeError, match='injected failure'):
            upgrade(engine, FailingMetadata())
        assert 'status' not in {c['name'] for c in inspect(engine).get_columns('assignments')}
        assert 'version' not in {c['name'] for c in inspect(engine).get_columns('submissions')}
        assert list(tmp_path.glob('failure.before-v2-*.db'))
        upgrade(engine, Base.metadata)
        with engine.connect() as conn:
            conn.exec_driver_sql('ALTER TABLE submissions DROP COLUMN version')
            conn.commit()
        with pytest.raises(RuntimeError, match='Incomplete schema'):
            upgrade(engine, Base.metadata)
    finally:
        engine.dispose()
