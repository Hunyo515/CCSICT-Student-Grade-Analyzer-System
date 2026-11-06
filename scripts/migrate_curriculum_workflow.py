"""Inspect/apply the single-curriculum workflow migration and import BSDSA.

Existing subjects and academic history are preserved. Oracle DDL commits
individually; each operation is resumable. Existing imported rows are never
overwritten. Run without --apply first to inspect the plan.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config
from app.curriculum import source_curriculum

COLUMNS = {
    'LECTURE_UNITS': 'NUMBER(3)', 'LAB_UNITS': 'NUMBER(3)',
    'PREREQUISITE_TEXT': 'VARCHAR2(500)', 'UNITS_NOTE': 'VARCHAR2(12)',
    'IS_ARCHIVED': 'NUMBER(1) DEFAULT 0 NOT NULL CHECK (is_archived IN (0,1))',
}


def import_rows():
    rows = []
    for year, data in enumerate(source_curriculum('BSDSA')['years'], 1):
        for semester, term in enumerate(data['semesters'], 1):
            for c in term['courses']:
                rows.append(dict(code=c['code'], name=c['title'], units=int(c['units'].strip('()')),
                    year_level=('1st','2nd','3rd','4th')[year-1]+' Year',
                    semester=('1st' if semester==1 else '2nd')+' Semester',
                    lecture=int(c['lecture']) if c['lecture'] else None,
                    lab=int(c['laboratory']) if c['laboratory'] else None,
                    prerequisite=c['prerequisite'] or None,
                    note=c['units'] if c['units'].startswith('(') else None))
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):
        raise ValueError('Invalid configured schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN) as conn:
        conn.current_schema=owner
        conn.call_timeout=15000
        with conn.cursor() as c:
            c.execute('SELECT * FROM subjects ORDER BY subject_id')
            old=[dict(zip([d[0].lower() for d in c.description],row)) for row in c]
            if args.apply:
                backup=Path(__file__).resolve().parents[1]/'audit'/'curriculum-migration'
                backup.mkdir(exist_ok=True)
                path=backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-subjects.json')
                path.write_text(json.dumps(old,default=str,indent=2),encoding='utf-8')
                print('Subject snapshot:',path)
            c.execute("SELECT column_name FROM all_tab_columns WHERE owner=:o AND table_name='SUBJECTS'",o=owner)
            columns={r[0] for r in c}
            for column, definition in COLUMNS.items():
                if column not in columns:
                    print('ADD',column)
                    if args.apply:c.execute(f'ALTER TABLE subjects ADD {column} {definition}')
            c.execute("""SELECT cc.constraint_name, cc.column_name FROM all_cons_columns cc
                JOIN all_constraints ac ON ac.owner=cc.owner AND ac.constraint_name=cc.constraint_name
                WHERE cc.owner=:o AND cc.table_name='SUBJECTS' AND ac.constraint_type='U'
                ORDER BY cc.constraint_name, cc.position""",o=owner)
            unique={}
            for name,column in c:unique.setdefault(name,[]).append(column)
            # Same course number may occur in multiple programs; source DSA 315
            # also denotes two different titles. Keep both codes without inventing one.
            if 'UQ_CURRICULUM_SUBJECT' not in unique:
                print('ADD unique program / code / title constraint')
                if args.apply:c.execute('ALTER TABLE subjects ADD CONSTRAINT uq_curriculum_subject UNIQUE (program, subject_code, subject_name)')
            for name,columns in unique.items():
                if columns==['SUBJECT_CODE']:
                    if not re.fullmatch(r'[A-Z][A-Z0-9_$#]{0,127}',name):raise ValueError('Unexpected constraint identifier')
                    print('REPLACE global subject-code uniqueness:',name)
                    if args.apply:c.execute(f'ALTER TABLE subjects DROP CONSTRAINT {name}')
            existing={(r['program'],r['subject_code'],r['subject_name']) for r in old}
            pending=[r for r in import_rows() if ('BSDSA',r['code'],r['name']) not in existing]
            print('New BSDSA subjects:',len(pending))
            if args.apply and pending:
                c.executemany("""INSERT INTO subjects
                    (program,subject_code,subject_name,units,year_level,semester_offered,
                     lecture_units,lab_units,prerequisite_text,units_note)
                    VALUES ('BSDSA',:code,:name,:units,:year_level,:semester,:lecture,:lab,:prerequisite,:note)""",pending)
                conn.commit()
            print('Existing subjects retained:',len(old))


if __name__=='__main__':main()
