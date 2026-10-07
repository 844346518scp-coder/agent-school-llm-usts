"""Version 1 of additive enrollment/mail tables; platform schema v3 stays intact."""
from pathlib import Path
from contextlib import closing
import sqlite3
from uuid import uuid4
from sqlalchemy import inspect, text

def upgrade_community(engine, metadata):
    tables = inspect(engine).get_table_names()
    if 'community_schema_migrations' in tables:
        with engine.connect() as conn:
            version = conn.scalar(text('SELECT MAX(version) FROM community_schema_migrations'))
        if version != 1:
            raise RuntimeError('Unsupported community schema')
        for table in metadata.sorted_tables:
            if table.name not in tables or not {c.name for c in table.columns} <= {c['name'] for c in inspect(engine).get_columns(table.name)}:
                raise RuntimeError('Incomplete community schema')
        return None
    backup = None
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('Community migration currently supports SQLite only')
    path = engine.url.database
    if path and path != ':memory:' and tables:
        original = Path(path).resolve()
        backup = original.with_name(original.stem + '.before-community-v1-' + uuid4().hex[:12] + '.db')
        with closing(sqlite3.connect(original)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Community backup verification failed')
    with engine.connect() as conn:
        conn.exec_driver_sql('BEGIN EXCLUSIVE')
        try:
            metadata.create_all(conn)
            conn.execute(text('INSERT INTO community_schema_migrations(version) VALUES (1)'))
            conn.commit()
        except Exception:
            conn.rollback(); raise
    return backup
