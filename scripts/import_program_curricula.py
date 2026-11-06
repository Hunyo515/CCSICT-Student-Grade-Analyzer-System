"""Import verified BSCS/BSIT/BSIS/BLIS source rows without overwriting records."""
import argparse,json,re,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config
from app.curriculum import curriculum_rows

PROGRAMS=('BSCS','BSIT','BSIS','BLIS')

def plan(existing):
    old={(r['program'],r['subject_code'],r['subject_name']):r for r in existing}
    pending=[];conflicts=[];keys=set()
    for program in PROGRAMS:
        for row in curriculum_rows(program):
            key=(program,row['code'],row['name'])
            if key in keys:raise ValueError(f'Duplicate source identity: {key}')
            keys.add(key)
            if len(row['code'].encode())>20 or len(row['name'].encode())>150:raise ValueError(f'Source exceeds schema limits: {key}')
            previous=old.get(key)
            if not previous:pending.append(row);continue
            for target,source in [('units','units'),('year_level','year_level'),('semester_offered','semester'),('lecture_units','lecture'),('lab_units','lab'),('prerequisite_text','prerequisite'),('units_note','note')]:
                if previous.get(target)!=row[source]:conflicts.append(dict(identity=key,field=target,existing=previous.get(target),source=row[source]))
    return pending,conflicts

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',owner):raise ValueError('Invalid schema')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
        conn.current_schema=owner;conn.call_timeout=15000;c=conn.cursor()
        c.execute('SELECT * FROM subjects ORDER BY subject_id');columns=[d[0].lower() for d in c.description];old=[dict(zip(columns,r)) for r in c]
        pending,conflicts=plan(old)
        for program in PROGRAMS:print(program,'source:',len(curriculum_rows(program)),'new:',sum(r['program']==program for r in pending))
        if conflicts:
            print(json.dumps(conflicts,default=str,indent=2));raise RuntimeError('Existing matching records differ. Review before importing; no data changed.')
        if not args.apply:return
        if pending:
            root=Path(__file__).resolve().parents[1]/'audit/program-curricula';root.mkdir(parents=True,exist_ok=True)
            backup=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-subjects-before-import.json')
            backup.write_text(json.dumps(old,default=str,indent=2),encoding='utf-8');print('Backup:',backup)
            c.executemany('''INSERT INTO subjects(program,subject_code,subject_name,units,year_level,semester_offered,lecture_units,lab_units,prerequisite_text,units_note)
                VALUES(:program,:code,:name,:units,:year_level,:semester,:lecture,:lab,:prerequisite,:note)''',pending)
            c.execute('SELECT * FROM subjects');columns=[d[0].lower() for d in c.description];after=[dict(zip(columns,r)) for r in c]
            remaining,issues=plan(after)
            if remaining or issues:raise RuntimeError('Post-import source verification failed; transaction will be rolled back.')
            by_id={r['subject_id']:r for r in after}
            if any(by_id.get(r['subject_id'])!=r for r in old):raise RuntimeError('An existing row changed; transaction will be rolled back.')
            conn.commit();print('Imported',len(pending),'verified subjects. All existing rows preserved.')
        else:print('No changes needed. All source subjects are already present.')

if __name__=='__main__':main()
