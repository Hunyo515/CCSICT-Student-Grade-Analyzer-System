"""Back up and clear student/faculty rosters. Run explicitly with --apply."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracledb
from config import Config

TABLES = ('USERS', 'STUDENTS', 'TEACHERS', 'TEACHER_SUBJECTS', 'ENROLLMENTS',
          'GRADE_CATEGORIES', 'GRADE_COMPONENTS', 'GRADES', 'GRADE_VERSIONS',
          'STUDENT_TERM_MEMBERSHIPS', 'NOTIFICATIONS', 'ACTIVITY_LOG',
          'ASSESSMENTS', 'ASSESSMENT_SCORES', 'ITEM_SCORES', 'MARKS',
          'TEACHER_ASSIGNMENTS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    owner = (Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', owner):
        parser.error('Invalid schema identifier.')
    with oracledb.connect(user=Config.ORACLE_USER, password=Config.ORACLE_PASSWORD,
                          dsn=Config.ORACLE_DSN, tcp_connect_timeout=5) as conn:
        conn.current_schema = owner
        conn.call_timeout = 15000
        cur = conn.cursor()
        cur.execute('SELECT role, COUNT(*) FROM users GROUP BY role')
        before = dict(cur.fetchall())
        print('Before:', before)
        if not args.apply:
            return
        # Block concurrent roster writes until the backup and deletion commit.
        for table in sorted(TABLES):
            cur.execute(f'LOCK TABLE {table} IN EXCLUSIVE MODE WAIT 5')
        snapshot = {}
        for table in TABLES:
            cur.execute(f'SELECT * FROM {table}')
            columns = [c[0] for c in cur.description]
            snapshot[table] = [dict(zip(columns, [v.read() if hasattr(v, 'read') else v for v in row])) for row in cur]
        directory = Path(__file__).resolve().parents[1] / 'instance' / 'roster-backups'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.zip')
        with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('roster.json', json.dumps(snapshot, default=str))
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Backup verification failed; no data removed.')
        print('Backup:', path)
        # Historical versions and memberships have non-cascading references.
        cur.execute('DELETE FROM grade_versions WHERE assignment_id IN (SELECT assignment_id FROM teacher_subjects) OR actor_user_id IN (SELECT user_id FROM users WHERE role IN (\'student\',\'faculty\'))')
        cur.execute('DELETE FROM student_term_memberships')
        # Retired schema tables lack foreign keys to the current roster.
        for table in ('ASSESSMENT_SCORES', 'ITEM_SCORES', 'MARKS', 'ASSESSMENTS', 'TEACHER_ASSIGNMENTS'):
            cur.execute(f'DELETE FROM {table}')
        cur.execute("DELETE FROM notifications WHERE link IN ('/admin/students','/admin/teachers')")
        cur.execute('DELETE FROM teacher_subjects WHERE teacher_id IS NULL')
        cur.execute("DELETE FROM users WHERE role IN ('student','faculty')")
        for table in ('STUDENTS', 'TEACHERS', 'TEACHER_SUBJECTS', 'ENROLLMENTS', 'GRADES'):
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            if cur.fetchone()[0]:
                raise RuntimeError(f'{table} was not cleared; rolling back.')
        cur.execute('SELECT COUNT(*) FROM users WHERE role=\'admin\'')
        if cur.fetchone()[0] != before.get('admin', 0):
            raise RuntimeError('Admin count changed; rolling back.')
        cur.execute("INSERT INTO activity_log(message) VALUES ('Student and faculty rosters reset at owner request; backup saved locally.')")
        conn.commit()
        cur.execute('SELECT role, COUNT(*) FROM users GROUP BY role')
        print('After:', dict(cur.fetchall()))


if __name__ == '__main__':
    main()
