-- Review/run as DBA, substituting your owner/runtime usernames.
-- Create the runtime account with a securely managed password outside this file.
-- Do not grant DBA, RESOURCE, CREATE TABLE, DROP ANY TABLE or grant options.
DEFINE owner = STUDENT
DEFINE runtime = CCT_APP
GRANT CREATE SESSION TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..users TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..school_terms TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..subjects TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..teachers TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..students TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..teacher_subjects TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..enrollments TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..grade_categories TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..grade_components TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..grades TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..notifications TO &runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON &owner..activity_log TO &runtime;
-- Set ORACLE_USER to runtime and ORACLE_SCHEMA to owner.
-- Test row locks, identities and term activation in staging with this account.
-- Database network access must be restricted to the application/backup hosts.
