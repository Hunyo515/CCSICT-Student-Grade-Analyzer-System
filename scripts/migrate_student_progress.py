"""Add registration and progression fields without removing historical records."""
import argparse,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;c=conn.cursor()
        for table,col,definition in [('students','age','NUMBER(3) CHECK(age BETWEEN 1 AND 120)'),('students','progress_school_year','NUMBER(4)'),('teachers','program',"VARCHAR2(20) CHECK(program IN ('BSDSA','BSCS','BSIT','BSIS','BLIS'))")]:
            c.execute('SELECT column_name FROM all_tab_columns WHERE owner=:o AND table_name=:t AND column_name=:c',o=owner,t=table.upper(),c=col.upper())
            if not c.fetchone():
                print('Add',table,col)
                if args.apply:c.execute(f'ALTER TABLE {table} ADD {col} {definition}')
        if args.apply:
            c.execute("UPDATE students SET progress_school_year=(SELECT TO_NUMBER(SUBSTR(school_year,1,4)) FROM school_terms WHERE is_active=1) WHERE progress_school_year IS NULL")
            conn.commit();print('Migration applied; existing ages and faculty programs left blank.')
if __name__=='__main__':main()
