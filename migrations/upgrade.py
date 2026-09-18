"""Versioned SQLite upgrade. Run only with old application writers stopped."""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

from sqlalchemy import inspect, text

VERSION = 2


def upgrade(engine, metadata):
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('0.2 migrations currently support SQLite only; PostgreSQL requires a separately verified migration.')
    tables = inspect(engine).get_table_names()
    if 'schema_migrations' in tables:
        with engine.connect() as conn:
            version = conn.scalar(text('SELECT MAX(version) FROM schema_migrations'))
        if version == VERSION:
            # Do not silently accept a partially upgraded database.
            for table in metadata.sorted_tables:
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
        backup = path.with_name(f'{path.stem}.before-v2-{uuid4().hex[:12]}.db')
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
            ):
                if table in existing and column not in {c['name'] for c in inspector.get_columns(table)}:
                    conn.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
            metadata.create_all(conn)
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
