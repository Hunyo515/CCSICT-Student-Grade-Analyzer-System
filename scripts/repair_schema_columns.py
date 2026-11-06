"""Repair missing curriculum/revision columns without replacing existing data.

Defaults to inspection only; pass --apply to add missing columns.
"""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

COLUMNS = (
    ('SUBJECTS', 'PROGRAM', 'VARCHAR2(20)'),
    ('SUBJECTS', 'SEMESTER_OFFERED', 'VARCHAR2(20)'),
    ('SUBJECTS', 'PREREQUISITE_SUBJECT_ID',
     'NUMBER REFERENCES subjects(subject_id) ON DELETE SET NULL'),
    ('TEACHER_SUBJECTS', 'REVISION', 'NUMBER DEFAULT 0 NOT NULL'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    owner = (Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,29}', owner):
        parser.error('The configured schema must be a simple Oracle identifier.')
    with oracledb.connect(user=Config.ORACLE_USER, password=Config.ORACLE_PASSWORD,
                          dsn=Config.ORACLE_DSN, tcp_connect_timeout=5) as conn:
        conn.call_timeout = 15000
        conn.current_schema = owner
        with conn.cursor() as cursor:
            for table, column, definition in COLUMNS:
                cursor.execute('SELECT column_name FROM all_tab_columns '
                               'WHERE owner=:owner AND table_name=:table_name',
                               owner=owner, table_name=table)
                existing = {row[0] for row in cursor}
                if not existing:
                    raise RuntimeError(f'{table} is missing or inaccessible; no table will be created.')
                if column in existing:
                    print(f'OK {table}.{column}')
                    continue
                sql = f'ALTER TABLE {table} ADD {column} {definition}'
                if args.apply:
                    cursor.execute(sql)
                    print(f'ADDED {table}.{column}')
                else:
                    print(f'PENDING {sql}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
