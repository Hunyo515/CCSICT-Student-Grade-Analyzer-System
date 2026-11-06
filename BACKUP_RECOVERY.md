# Backup and recovery runbook

## Prepare once

Install Oracle Data Pump clients matching the database. A DBA must create an
Oracle DIRECTORY named CCT_BACKUP_DIR pointing at a protected folder on the
**database server**, grant the backup operator READ/WRITE on it, and configure
an Oracle secure external password store (wallet) and TNS alias CCTDB. Use an
operator with the required export/import and flashback privileges; keep wallet
files readable only by the service account. No passwords go in command lines.

## Back up

Run `python scripts/backup_recovery.py backup --service CCTDB --schema STUDENT`.
This exports a consistent schema snapshot using a single flashback timestamp.
Keep the .dmp and Data Pump .log together. Only exit code zero is success;
inspect the log for object failures. Configure Windows Task Scheduler to run
this daily under the backup service account, with an alert on nonzero exit.
The scripts do not silently install a schedule or delete old backups.

Copy successful dumps to encrypted off-host storage and record SHA-256 checksums.
Retain 7 daily and 4 weekly verified copies according to school policy. Back up
application source, dependency versions, and database migrations alongside each
release. Store .env and wallet secrets separately in a restricted secret store.
Do not restore instance/security.sqlite3: it holds rate limits and grade-import
previews, not academic records. Recreating it invalidates active sessions and
previews. Rotate SECRET_KEY on recovery to invalidate session cookies.

## Recover and validate

1. Preserve the failed system and logs. Choose a successful dump and verify its
   recorded checksum. Recreate the application's Python environment from requirements.txt.
2. Have the DBA create an **empty, separate** schema, for example STUDENT_RECOVERY,
   with appropriate tablespace quota and privileges. The tool refuses the source
   schema as a target; it does not overwrite existing tables (SKIP). A nonempty
   target is not a valid recovery rehearsal; use a fresh empty target. The script
   checks DBA_USERS and DBA_OBJECTS through SQL*Plus before import and refuses an
   unverified/nonempty target. The operator needs read access to those metadata
   views; missing privileges fail closed.
3. Run `python scripts/backup_recovery.py recover --service CCTDB --schema STUDENT --dump cct_TIMESTAMP.dmp --target STUDENT_RECOVERY`.
4. Inspect the import log and verify all expected tables, constraints, sequences,
   identity columns and row counts. Compare representative student totals,
   class rankings, enrollment counts and published grades with the source/backup
   records. Confirm a newly created record gets a unique identity.
5. Start an isolated application instance against STUDENT_RECOVERY. Configure a
   fresh SECRET_KEY and HTTPS. Test password login for each role, permissions, a draft
   score save, CSV import, publication, and dashboard totals. Do not send test
   notifications to real students; use isolated mail delivery.
6. Once validation passes, schedule a maintenance window and approve cutover.
   Stop application writers, take a final backup when possible, point ORACLE_USER
   and ORACLE_PASSWORD at the restored schema, restart, and smoke-test. Preserve
   the previous schema for rollback; switch configuration back if checks fail.

Rehearse quarterly on a separate database. Record dump time, restore duration,
row counts, test results and operator. Daily backups imply up to 24 hours of data
loss; a recovery-time target must be established from measured rehearsals. For
point-in-time database recovery, have the DBA configure and test RMAN/archivelogs;
Data Pump schema exports are not a substitute for physical database backups.

No live backup or restore has been run by this implementation task.
