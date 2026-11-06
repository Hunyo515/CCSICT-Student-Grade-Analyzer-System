"""Add optional activity dates without changing existing records."""
import argparse,re,sys
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
        c.execute("SELECT column_name FROM all_tab_columns WHERE owner=:o AND table_name='GRADE_COMPONENTS' AND column_name='ACTIVITY_DATE'",o=owner)
        if c.fetchone():print('Activity dates already available.');return
        if not args.apply:print('Pending: optional activity_date column.');return
        c.execute('ALTER TABLE grade_components ADD activity_date DATE')
        print('Applied: optional activity dates. Existing records preserved.')

if __name__=='__main__':main()
