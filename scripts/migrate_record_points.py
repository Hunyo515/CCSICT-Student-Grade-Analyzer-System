"""Use class-record raw-total/HPS computation for active editable classes."""
import argparse,json,re,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;conn.call_timeout=15000;c=conn.cursor()
        where="status IN ('DRAFT','IN_PROGRESS') AND term_id IN (SELECT term_id FROM school_terms WHERE is_active=1) AND aggregation<>'POINTS'"
        c.execute('SELECT assignment_id,aggregation,revision FROM teacher_subjects WHERE '+where)
        rows=c.fetchall();print('Editable classes to switch:',len(rows))
        if not args.apply:return
        if rows:
            root=Path(__file__).resolve().parents[1]/'instance'/'migration-backups';root.mkdir(parents=True,exist_ok=True)
            path=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-record-points.json')
            path.write_text(json.dumps(rows,default=str),encoding='utf-8')
            c.execute("UPDATE teacher_subjects SET aggregation='POINTS',revision=revision+1 WHERE "+where);conn.commit()
        c.execute("ALTER TABLE teacher_subjects MODIFY aggregation DEFAULT 'POINTS'")
        print('Applied: raw-total/HPS computation. Published and historical records preserved.')

if __name__=='__main__':main()
