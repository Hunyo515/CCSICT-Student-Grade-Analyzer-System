"""Read-only deployment preflight. Never prints secret values or changes data."""
import argparse
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',action='store_true',help='Connect to the configured Oracle service and inspect metadata')
    args=parser.parse_args()
    checks={
        'strong_secret_configured':len(Config.SECRET_KEY)>=32 and not Config.SECRET_KEY.startswith('change-me'),
        'oracle_credentials_configured':bool(Config.ORACLE_USER and Config.ORACLE_PASSWORD),
        'secure_cookies_enabled':Config.SESSION_COOKIE_SECURE,
        'email_delivery_configured':bool(Config.MAIL_HOST and Config.MAIL_FROM),
    }
    if args.database and checks['oracle_credentials_configured']:
        import oracledb
        try:
            with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN,tcp_connect_timeout=5) as conn:
                conn.call_timeout=10000
                owner=(Config.ORACLE_SCHEMA or Config.ORACLE_USER).upper()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT column_name FROM all_tab_columns WHERE owner=:owner AND table_name='TEACHER_SUBJECTS'",owner=owner)
                    checks['rebuild_migration_applied']={'REVISION','AGGREGATION','ROUNDING_RULE'}.issubset({r[0] for r in cursor})
                    cursor.execute("SELECT privilege FROM session_privs")
                    privileges={r[0] for r in cursor}
                    checks['runtime_has_no_ddl_or_any_privileges']=not any('ANY' in p or p.startswith(('CREATE TABLE','ALTER SYSTEM','CREATE USER','DROP USER')) for p in privileges)
                    cursor.execute("SELECT role FROM session_roles")
                    checks['runtime_not_dba']='DBA' not in {r[0] for r in cursor}
                    cursor.execute("SELECT index_name FROM all_indexes WHERE owner=:owner AND index_name='UQ_ONE_ACTIVE_TERM'",owner=owner)
                    checks['single_active_term_index']=bool(cursor.fetchone())
                    cursor.execute("SELECT constraint_name,status,validated FROM all_constraints WHERE owner=:owner AND constraint_name IN ('CK_SUBJECT_UNITS','CK_GRADE_RANGE','CK_COMPONENT_WEIGHT','CK_CATEGORY_WEIGHT')",owner=owner)
                    rows=cursor.fetchall()
                    checks['range_constraints_validated']=len(rows)==4 and all(r[1:] == ('ENABLED','VALIDATED') for r in rows)
                    checks['separate_runtime_account']=Config.ORACLE_USER.upper()!=owner
        except Exception as error:
            checks['oracle_metadata_connection']=False
            print('Oracle metadata check failed:',type(error).__name__)
    elif args.database:
        checks['oracle_metadata_connection']=False
    for key,value in checks.items():print(('PASS' if value else 'BLOCKED')+' '+key)
    print('This preflight does not certify backups, TLS/proxy setup, or production load capacity.')
    return 0 if all(checks.values()) else 1

if __name__=='__main__':sys.exit(main())
