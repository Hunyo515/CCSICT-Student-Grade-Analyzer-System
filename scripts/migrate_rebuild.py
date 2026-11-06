"""Resumable additive Oracle upgrade. Preview by default; --apply snapshots first."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

COLUMNS = {
    'USERS': {'MUST_CHANGE_PASSWORD': 'NUMBER(1) DEFAULT 0 NOT NULL CHECK(must_change_password IN (0,1))'},
    'STUDENTS': {'FIRST_NAME':'VARCHAR2(50)','MIDDLE_NAME':'VARCHAR2(50)','LAST_NAME':'VARCHAR2(50)'},
    'SCHOOL_TERMS': {'ENLISTMENT_OPEN':'NUMBER(1) DEFAULT 0 NOT NULL CHECK(enlistment_open IN (0,1))'},
    'TEACHER_SUBJECTS': {
        'AGGREGATION': "VARCHAR2(10) DEFAULT 'LEGACY' NOT NULL CHECK (aggregation IN ('LEGACY','EQUAL','POINTS'))",
        'ROUNDING_RULE': "VARCHAR2(10) DEFAULT 'UNSET' NOT NULL CHECK (rounding_rule IN ('UNSET','HALF_UP','FLOOR'))",
    },
    'GRADE_COMPONENTS': {'MAXIMUM_SCORE': 'NUMBER(8,2) DEFAULT 100 NOT NULL CHECK (maximum_score>0)'},
}
TABLES = {
    'GRADE_VERSIONS': '''CREATE TABLE grade_versions (
        version_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        assignment_id NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id),
        kind VARCHAR2(15) NOT NULL CHECK (kind IN ('RELEASE','SUBMISSION','PUBLICATION','RETURN')),
        actor_user_id NUMBER REFERENCES users(user_id) ON DELETE SET NULL,
        actor_name VARCHAR2(150),
        source_version_id NUMBER REFERENCES grade_versions(version_id),
        revision NUMBER NOT NULL, payload CLOB NOT NULL, reason VARCHAR2(500),
        created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL)''',
    'ACADEMIC_SECTIONS': '''CREATE TABLE academic_sections (
        section_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        term_id NUMBER NOT NULL REFERENCES school_terms(term_id),
        program VARCHAR2(20) NOT NULL, year_level VARCHAR2(20) NOT NULL,
        section_name VARCHAR2(20) NOT NULL,
        CONSTRAINT uq_academic_section UNIQUE(term_id,program,year_level,section_name))''',
    'STUDENT_TERM_MEMBERSHIPS': '''CREATE TABLE student_term_memberships (
        membership_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        student_id NUMBER NOT NULL REFERENCES students(student_id),
        term_id NUMBER NOT NULL REFERENCES school_terms(term_id),
        section_id NUMBER NOT NULL REFERENCES academic_sections(section_id),
        CONSTRAINT uq_student_term_member UNIQUE(student_id,term_id))''',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner): raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN) as conn:
        conn.current_schema=owner
        with conn.cursor() as c:
            if args.apply:
                root=Path(__file__).resolve().parents[1]/'audit'/'rebuild-migration'
                root.mkdir(parents=True,exist_ok=True)
                stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
                c.execute('SET TRANSACTION READ ONLY')
                c.execute('SELECT table_name FROM all_tables WHERE owner=:o',o=owner)
                names=[r[0] for r in c if re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',r[0])]
                snapshot={}
                for name in names:
                    c.execute(f'SELECT * FROM {name}')
                    columns=[d[0].lower() for d in c.description]
                    snapshot[name]=[dict(zip(columns,[v.read() if hasattr(v,'read') else v for v in row])) for row in c]
                (root/f'{stamp}.json').write_text(json.dumps(snapshot,default=str),encoding='utf-8')
                conn.rollback()
                print('Pre-migration logical snapshot saved. Use Data Pump for operational recovery.')
            for table,columns in COLUMNS.items():
                c.execute('SELECT column_name FROM all_tab_columns WHERE owner=:o AND table_name=:t',o=owner,t=table)
                existing={r[0] for r in c}
                for name,definition in columns.items():
                    if name not in existing:
                        print('ADD',table,name)
                        if args.apply:c.execute(f'ALTER TABLE {table} ADD {name} {definition}')
            c.execute('SELECT table_name FROM all_tables WHERE owner=:o',o=owner)
            existing={r[0] for r in c}
            for table,sql in TABLES.items():
                if table not in existing:
                    print('CREATE',table)
                    if args.apply:c.execute(sql)
            c.execute("SELECT constraint_name,search_condition_vc FROM all_constraints WHERE owner=:o AND table_name='TEACHER_SUBJECTS' AND constraint_type='C'",o=owner)
            for name,condition in c.fetchall():
                if 'STATUS' in (condition or '').upper() and 'PUBLISHED' in condition and 'SUBMITTED' not in condition:
                    print('UPGRADE grade state constraint')
                    if args.apply:
                        if not re.fullmatch(r'[A-Z][A-Z0-9_$#]{0,127}',name): raise ValueError('Invalid constraint')
                        c.execute(f'ALTER TABLE teacher_subjects DROP CONSTRAINT {name}')
            if args.apply:
                c.execute("SELECT constraint_name FROM all_constraints WHERE owner=:o AND constraint_name='CK_CLASS_REVIEW_STATE'",o=owner)
                if not c.fetchone():c.execute("ALTER TABLE teacher_subjects ADD CONSTRAINT ck_class_review_state CHECK(status IN ('DRAFT','IN_PROGRESS','SUBMITTED','RETURNED','PUBLISHED'))")
                c.execute("SELECT index_name FROM all_indexes WHERE owner=:o AND index_name='IDX_GRADE_VERSIONS_CLASS'",o=owner)
                if not c.fetchone():c.execute('CREATE INDEX idx_grade_versions_class ON grade_versions(assignment_id,kind,version_id)')
            ranges=[('SUBJECTS','CK_SUBJECT_UNITS','units BETWEEN 1 AND 6'),
                    ('GRADES','CK_GRADE_RANGE','max_score > 0 AND (score IS NULL OR score BETWEEN 0 AND max_score)'),
                    ('GRADE_COMPONENTS','CK_COMPONENT_WEIGHT','weight_percent BETWEEN 0 AND 100'),
                    ('GRADE_CATEGORIES','CK_CATEGORY_WEIGHT','weight_percent BETWEEN 0 AND 100')]
            for table,name,condition in ranges:
                c.execute('SELECT constraint_name FROM all_constraints WHERE owner=:o AND constraint_name=:name',o=owner,name=name)
                if c.fetchone():continue
                c.execute(f'SELECT COUNT(*) FROM {table} WHERE NOT ({condition})')
                if c.fetchone()[0]:print('REVIEW invalid legacy values before adding',name);continue
                print('ADD',name)
                if args.apply:c.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})')
            indexes=[('UQ_ONE_ACTIVE_TERM','SELECT COUNT(*) FROM school_terms WHERE is_active=1',
                      'CREATE UNIQUE INDEX uq_one_active_term ON school_terms(CASE WHEN is_active=1 THEN 1 ELSE NULL END)'),
                     ('UQ_CLASS_SUBJECT_SECTION','SELECT COUNT(*) FROM (SELECT subject_id,term_id,LOWER(TRIM(section)) FROM teacher_subjects GROUP BY subject_id,term_id,LOWER(TRIM(section)) HAVING COUNT(*)>1)',
                      'CREATE UNIQUE INDEX uq_class_subject_section ON teacher_subjects(subject_id,term_id,LOWER(TRIM(section)))'),
                     ('UQ_ONE_ENLIST_TERM','SELECT COUNT(*) FROM school_terms WHERE enlistment_open=1',
                      'CREATE UNIQUE INDEX uq_one_enlist_term ON school_terms(CASE WHEN enlistment_open=1 THEN 1 ELSE NULL END)')]
            for name,audit,definition in indexes:
                c.execute('SELECT index_name FROM all_indexes WHERE owner=:o AND index_name=:name',o=owner,name=name)
                if c.fetchone():continue
                c.execute(audit);violations=c.fetchone()[0]
                if violations>(1 if name in ('UQ_ONE_ACTIVE_TERM','UQ_ONE_ENLIST_TERM') else 0):print('REVIEW duplicate legacy records before adding',name);continue
                print('ADD',name)
                if args.apply:c.execute(definition)
            if args.apply:
                # Preserve existing assessment scales when every old score agrees.
                c.execute('''UPDATE grade_components gc SET maximum_score=(SELECT MAX(g.max_score) FROM grades g WHERE g.component_id=gc.component_id)
                    WHERE EXISTS(SELECT 1 FROM teacher_subjects ts WHERE ts.assignment_id=gc.assignment_id AND ts.aggregation='LEGACY')
                    AND EXISTS(SELECT 1 FROM grades g WHERE g.component_id=gc.component_id GROUP BY g.component_id HAVING COUNT(DISTINCT g.max_score)=1)''')
            conn.commit()
    print('Applied.' if args.apply else 'Preview only. Run with --apply to upgrade.')


if __name__=='__main__':main()
