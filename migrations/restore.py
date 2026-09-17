"""Restore a SQLite backup to a NEW path, preserving every existing database."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def restore(backup: Path, output: Path):
    backup, output = backup.resolve(), output.resolve()
    if not backup.is_file():
        raise ValueError('Backup does not exist.')
    if output.exists():
        raise ValueError('Output already exists; choose a new database path.')
    with closing(sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity check failed.')
        # Exclusive file creation prevents accidental overwrites.
        with output.open('xb'):
            pass
        with closing(sqlite3.connect(output)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Restored database failed verification; do not use it.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(f'Restored and verified: {restore(args.backup, args.output)}')
