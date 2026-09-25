--------------------------------------------------------------------------
-- Migration 003 — Analytics support (sex + enrollment type on students)
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

ALTER TABLE students ADD sex VARCHAR2(10) CHECK (sex IN ('MALE', 'FEMALE'));

ALTER TABLE students ADD enrollment_type VARCHAR2(10) DEFAULT 'REGULAR'
  CHECK (enrollment_type IN ('REGULAR', 'IRREGULAR'));

COMMIT;
