"""Enable faculty-defined semester grading without changing published results."""
import argparse,json,re,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');args=p.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;conn.call_timeout=15000;c=conn.cursor()
        c.execute("SELECT column_name FROM all_tab_columns WHERE owner=:o AND table_name='TEACHER_SUBJECTS' AND column_name='GRADING_MODEL'",o=owner)
        if c.fetchone():print('Flexible grading migration already applied.');return
        if not args.apply:print('Pending: class grading model; existing published classes retain their calculation.');return
        snapshot={}
        for name in ('TEACHER_SUBJECTS','GRADE_CATEGORIES','GRADE_COMPONENTS','GRADES'):
            c.execute(f'SELECT * FROM {name}');cols=[d[0] for d in c.description];snapshot[name]=[dict(zip(cols,r)) for r in c]
        root=Path(__file__).resolve().parents[1]/'instance'/'migration-backups';root.mkdir(parents=True,exist_ok=True)
        backup=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-flexible-grading.json');backup.write_text(json.dumps(snapshot,default=str),encoding='utf-8')
        c.execute("ALTER TABLE teacher_subjects ADD grading_model VARCHAR2(12) DEFAULT 'LEGACY' NOT NULL CHECK(grading_model IN ('LEGACY','FLEXIBLE'))")
        c.execute("UPDATE teacher_subjects SET grading_model='FLEXIBLE' WHERE status NOT IN ('PUBLISHED','SUBMITTED')")
        conn.commit();c.execute("ALTER TABLE teacher_subjects MODIFY grading_model DEFAULT 'FLEXIBLE'")
        print('Applied. Draft classes use faculty-defined components; published history preserved.');print('Backup:',backup)

if __name__=='__main__':main()
