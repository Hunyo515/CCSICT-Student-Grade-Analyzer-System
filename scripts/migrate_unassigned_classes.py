"""Allow real class enrollments before a faculty member is assigned."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;conn.call_timeout=15000
        cur=conn.cursor()
        cur.execute("SELECT nullable FROM all_tab_columns WHERE owner=:owner AND table_name='TEACHER_SUBJECTS' AND column_name='TEACHER_ID'",owner=owner)
        row=cur.fetchone()
        if not row:raise RuntimeError('TEACHER_SUBJECTS.TEACHER_ID missing')
        if row[0]=='Y':print('Already supports unassigned faculty.');return
        if not args.apply:print('Pending: ALTER TABLE teacher_subjects MODIFY (teacher_id NULL)');return
        cur.execute('SELECT * FROM teacher_subjects')
        columns=[d[0] for d in cur.description]
        snapshot=[dict(zip(columns,r)) for r in cur]
        directory=Path(__file__).resolve().parents[1]/'instance'/'migration-backups'
        directory.mkdir(parents=True,exist_ok=True)
        backup=directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-unassigned-classes.json')
        backup.write_text(json.dumps({'previous_nullable':row[0],'classes':snapshot},default=str),encoding='utf-8')
        cur.execute('ALTER TABLE teacher_subjects MODIFY (teacher_id NULL)')
        print('Applied: faculty assignment is optional; existing classes and enrollments preserved.')
        print('Backup:',backup)


if __name__=='__main__':main()
