"""Allow the nine-unit practicum subjects explicitly listed in the curricula."""
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
        c.execute("SELECT search_condition_vc FROM all_constraints WHERE owner=:o AND table_name='SUBJECTS' AND constraint_name='CK_SUBJECT_UNITS'",o=owner)
        existing=c.fetchone()
        if existing and re.sub(r'\s+',' ',existing[0].upper()).strip()=='UNITS BETWEEN 1 AND 9':print('Nine-unit practicum support already enabled.');return
        if not args.apply:print('Pending: widen subject units to 1 through 9; preserve existing records.');return
        c.execute('ALTER TABLE subjects ADD CONSTRAINT ck_subject_units_v2 CHECK(units BETWEEN 1 AND 9)')
        if existing:c.execute('ALTER TABLE subjects DROP CONSTRAINT ck_subject_units')
        c.execute('ALTER TABLE subjects RENAME CONSTRAINT ck_subject_units_v2 TO ck_subject_units')
        print('Applied: subjects support 1 through 9 units; existing data preserved.')

if __name__=='__main__':main()
