"""Allow unconfigured activity maxima; existing scores and maxima are preserved."""
import argparse,re,sys
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
        c.execute("SELECT nullable FROM all_tab_columns WHERE owner=:owner AND table_name='GRADE_COMPONENTS' AND column_name='MAXIMUM_SCORE'",owner=owner)
        nullable=c.fetchone()[0]
        if not args.apply:print('Highest possible score nullable:',nullable,'; apply to allow blank maxima for new activities.');return
        if nullable=='N':c.execute('ALTER TABLE grade_components MODIFY maximum_score NULL')
        c.execute('ALTER TABLE grade_components MODIFY maximum_score DEFAULT NULL')
        print('Applied: new activity maxima may be blank. Existing data preserved.')

if __name__=='__main__':main()
