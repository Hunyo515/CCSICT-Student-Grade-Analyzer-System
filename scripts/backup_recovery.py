"""Oracle Data Pump backup and isolated recovery. Requires Oracle client and wallet.

Examples (dump/log files live in the Oracle DIRECTORY on the database server):
  python scripts/backup_recovery.py backup --service CCTDB --schema STUDENT
  python scripts/backup_recovery.py recover --service CCTDB --schema STUDENT --dump cct_20261024T010000Z.dmp --target STUDENT_RECOVERY

Recovery only imports into a distinct, pre-created, EMPTY schema. It never
replaces the running application's schema. Validate recovery before cutover.
"""
import argparse
from datetime import datetime, timezone
import re
import subprocess


def identifier(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,29}', value):
        raise argparse.ArgumentTypeError('Use an Oracle identifier (letters, digits, underscore; max 30 characters).')
    return value.upper()


def dump_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.dmp', value):
        raise argparse.ArgumentTypeError('Use a dump filename ending in .dmp, without paths.')
    return value


def build_command(args):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    common = [f'userid=/@{args.service}', f'directory={args.directory}']
    if args.action == 'backup':
        return ['expdp', *common, f'schemas={args.schema}', f'dumpfile=cct_{stamp}.dmp', f'logfile=cct_{stamp}_backup.log', 'flashback_time=systimestamp', 'reuse_dumpfiles=NO']
    if not args.dump or not args.target or args.target == args.schema:
        raise ValueError('Recovery requires --dump and a --target schema different from the source schema.')
    return ['impdp', *common, f'dumpfile={args.dump}', f'logfile=cct_{stamp}_recovery.log', f'schemas={args.schema}', f'remap_schema={args.schema}:{args.target}', 'table_exists_action=SKIP']


def ensure_empty_target(args):
    # Identifiers have already passed argparse validation. Query only; never drop.
    sql = f"""WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0 VERIFY OFF ECHO OFF
SELECT CASE WHEN (SELECT COUNT(*) FROM dba_users WHERE username='{args.target}')=1
AND (SELECT COUNT(*) FROM dba_objects WHERE owner='{args.target}')=0
THEN 'CCT_TARGET_EMPTY' ELSE 'CCT_TARGET_NOT_EMPTY_OR_MISSING' END FROM dual;
EXIT
"""
    result = subprocess.run(['sqlplus','-L','-S',f'/@{args.service}'],input=sql,text=True,capture_output=True,check=False,timeout=30)
    if result.returncode or result.stdout.strip() != 'CCT_TARGET_EMPTY':
        raise SystemExit('Recovery target is missing, nonempty, or could not be verified. Use a pre-created empty schema and an operator with metadata visibility.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'recover'))
    parser.add_argument('--service', type=identifier, required=True, help='TNS alias with Oracle wallet credentials')
    parser.add_argument('--schema', type=identifier, required=True)
    parser.add_argument('--directory', type=identifier, default='CCT_BACKUP_DIR')
    parser.add_argument('--dump', type=dump_name)
    parser.add_argument('--target', type=identifier)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        command = build_command(args)
    except ValueError as error:
        parser.error(str(error))
    if args.dry_run:
        print(' '.join(command))
        return
    if args.action == "recover":
        ensure_empty_target(args)
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise SystemExit('Data Pump did not finish successfully. Review its database-server log before using the dump/recovery.')
    print('Data Pump completed. Review the server log and verify the dump/recovered schema using the recovery runbook.')


if __name__ == '__main__':
    main()

