"""Versioned SQLite upgrade. Run only with old application writers stopped."""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

from sqlalchemy import inspect, text

VERSION = 3


def upgrade(engine, metadata):
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('0.3 migrations currently support SQLite only; PostgreSQL requires a separately verified migration.')
    tables = inspect(engine).get_table_names()
    if 'schema_migrations' in tables:
        with engine.connect() as conn:
            version = conn.scalar(text('SELECT MAX(version) FROM schema_migrations'))
        if version == VERSION:
            # Do not silently accept a partially upgraded database.
            for table in metadata.sorted_tables:
                if table.name not in tables:
                    raise RuntimeError(f'Incomplete schema: {table.name}')
                actual = {c['name'] for c in inspect(engine).get_columns(table.name)}
                if not {c.name for c in table.columns} <= actual:
                    raise RuntimeError(f'Incomplete schema: {table.name}')
            return None
        if version and version > VERSION:
            raise RuntimeError('Database is newer than this application; refusing to start.')

    backup = None
    db_path = engine.url.database
    if tables and db_path and db_path != ':memory:':
        path = Path(db_path).resolve()
        backup = path.with_name(f'{path.stem}.before-v3-{uuid4().hex[:12]}.db')
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup verification failed; refusing migration.')

    with engine.connect() as conn:
        # Explicit BEGIN makes SQLite DDL transactional as well as excluding writers.
        conn.exec_driver_sql('BEGIN EXCLUSIVE')
        try:
            inspector = inspect(conn)
            existing = inspector.get_table_names()
            for table, column, definition in (
                ('assignments', 'status', "VARCHAR(20) NOT NULL DEFAULT 'published'"),
                ('submissions', 'version', 'INTEGER NOT NULL DEFAULT 1'),
                ('users', 'active', 'BOOLEAN NOT NULL DEFAULT 1'),
                ('users', 'must_change_password', 'BOOLEAN NOT NULL DEFAULT 0'),
                ('users', 'is_demo', 'BOOLEAN NOT NULL DEFAULT 0'),
                ('users', 'created_by', 'VARCHAR(40) REFERENCES users(id)'),
                ('assignments', 'class_id', 'VARCHAR(40) REFERENCES classrooms(id)'),
            ):
                if table in existing and column not in {c['name'] for c in inspector.get_columns(table)}:
                    conn.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
            metadata.create_all(conn)
            if 'users' in existing:
                teachers = conn.execute(text("SELECT id FROM users WHERE role='teacher'")).scalars().all()
                students = conn.execute(text("SELECT id FROM users WHERE role='student'")).scalars().all()
                timestamp = datetime.now(timezone.utc).isoformat()
                # Old versions exposed every published assignment to every old student.
                # Preserve that historical audience exactly, without granting new access.
                for teacher_id in teachers:
                    class_id = str(uuid4())
                    conn.execute(text('INSERT INTO classrooms(id,teacher_id,name,course,term,archived,created_at) VALUES (:id,:teacher,:name,:course,:term,0,:time)'),
                                 dict(id=class_id, teacher=teacher_id, name='历史教学班', course='高等数学', term='历史数据', time=timestamp))
                    for student_id in students:
                        conn.execute(text('INSERT INTO class_members(class_id,student_id,active) VALUES (:class_id,:student_id,1)'), dict(class_id=class_id, student_id=student_id))
                    conn.execute(text('UPDATE assignments SET class_id=:class_id WHERE teacher_id=:teacher AND class_id IS NULL'), dict(class_id=class_id, teacher=teacher_id))
                    for aid in conn.execute(text("SELECT id FROM assignments WHERE teacher_id=:teacher AND status!='draft'"), dict(teacher=teacher_id)).scalars():
                        for student_id in students:
                            conn.execute(text('INSERT OR IGNORE INTO assignment_recipients(assignment_id,student_id) VALUES (:aid,:sid)'), dict(aid=aid, sid=student_id))
                if len(teachers) == 1:
                    conn.execute(text("UPDATE users SET created_by=:teacher WHERE role='student' AND created_by IS NULL"), dict(teacher=teachers[0]))
                conn.execute(text("UPDATE users SET is_demo=1 WHERE (id='teacher' AND username='teacher') OR (id='student' AND username='student')"))
            conn.execute(text('INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (:v, :t)'),
                         {'v': VERSION, 't': datetime.now(timezone.utc).isoformat()})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return backup


if __name__ == '__main__':
    from backend.app.platform.database import Base, engine
    result = upgrade(engine, Base.metadata)
    print(f'Schema v{VERSION} ready. Backup: {result or "not needed"}')
