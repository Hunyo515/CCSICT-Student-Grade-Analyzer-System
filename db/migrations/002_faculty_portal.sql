--------------------------------------------------------------------------
-- Migration 002 — Faculty portal support
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

ALTER TABLE teacher_subjects ADD status VARCHAR2(20) DEFAULT 'DRAFT'
  CHECK (status IN ('DRAFT', 'IN_PROGRESS', 'PUBLISHED'));

COMMIT;
