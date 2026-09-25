--------------------------------------------------------------------------
-- Migration 004 — Class enrollment codes (faculty-section-detail)
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

ALTER TABLE teacher_subjects ADD join_code VARCHAR2(10) UNIQUE;

ALTER TABLE teacher_subjects ADD enrollment_open VARCHAR2(1) DEFAULT 'Y'
  CHECK (enrollment_open IN ('Y', 'N'));

COMMIT;
