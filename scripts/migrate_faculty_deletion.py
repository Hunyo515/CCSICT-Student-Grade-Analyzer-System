"""Preserve grade authorship while allowing deletion of faculty accounts."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;conn.call_timeout=15000;cur=conn.cursor()
        cur.execute("SELECT column_name,nullable FROM all_tab_columns WHERE owner=:o AND table_name='GRADE_VERSIONS'",o=owner)
        columns=dict(cur.fetchall())
        if 'ACTOR_USER_ID' not in columns:raise RuntimeError('Grade history table unavailable')
        cur.execute("""SELECT c.constraint_name,c.delete_rule FROM all_constraints c JOIN all_cons_columns cc
            ON cc.owner=c.owner AND cc.constraint_name=c.constraint_name
            WHERE c.owner=:o AND c.table_name='GRADE_VERSIONS' AND c.constraint_type='R' AND cc.column_name='ACTOR_USER_ID'""",o=owner)
        constraints=cur.fetchall()
        if 'ACTOR_NAME' in columns and columns['ACTOR_USER_ID']=='Y' and any(rule=='SET NULL' for _,rule in constraints):
            print('Faculty deletion schema already applied.');return
        if not args.apply:print('Pending: author-name snapshot and nullable author reference with ON DELETE SET NULL.');return
        snapshot={}
        for table in ('GRADE_VERSIONS','TEACHER_SUBJECTS','TEACHERS'):
            cur.execute(f'SELECT * FROM {table}');names=[d[0] for d in cur.description]
            snapshot[table]=[dict(zip(names,[v.read() if hasattr(v,'read') else v for v in row])) for row in cur]
        cur.execute('SELECT user_id,full_name FROM users');snapshot['AUTHOR_NAMES']=cur.fetchall()
        root=Path(__file__).resolve().parents[1]/'instance'/'migration-backups';root.mkdir(parents=True,exist_ok=True)
        backup=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-faculty-deletion.json')
        backup.write_text(json.dumps(snapshot,default=str),encoding='utf-8')
        if 'ACTOR_NAME' not in columns:cur.execute('ALTER TABLE grade_versions ADD actor_name VARCHAR2(150)')
        cur.execute('UPDATE grade_versions v SET actor_name=(SELECT u.full_name FROM users u WHERE u.user_id=v.actor_user_id) WHERE actor_name IS NULL')
        conn.commit()
        if columns['ACTOR_USER_ID']=='N':cur.execute('ALTER TABLE grade_versions MODIFY (actor_user_id NULL)')
        for name,rule in constraints:
            if rule=='SET NULL':continue
            if not re.fullmatch(r'[A-Z][A-Z0-9_$#]{0,127}',name):raise ValueError('Invalid constraint identifier')
            cur.execute(f'ALTER TABLE grade_versions DROP CONSTRAINT {name}')
        if not any(rule=='SET NULL' for _,rule in constraints):
            cur.execute('ALTER TABLE grade_versions ADD CONSTRAINT fk_grade_version_actor FOREIGN KEY(actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL')
        print('Applied. Faculty accounts can be deleted without deleting classes, grades, or author names.')
        print('Backup:',backup)


if __name__=='__main__':main()
