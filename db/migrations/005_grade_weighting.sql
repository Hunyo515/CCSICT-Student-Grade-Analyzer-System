--------------------------------------------------------------------------
-- Migration 005 — Lecture/Laboratory grade weighting (faculty-grade-weighting)
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

ALTER TABLE teacher_subjects ADD lecture_split NUMBER(5,2) DEFAULT 100;
ALTER TABLE teacher_subjects ADD lab_split NUMBER(5,2) DEFAULT 0;

ALTER TABLE grade_components ADD category VARCHAR2(10) DEFAULT 'LECTURE'
  CHECK (category IN ('LECTURE', 'LAB'));

COMMIT;
