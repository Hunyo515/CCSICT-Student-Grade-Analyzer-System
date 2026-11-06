--------------------------------------------------------------------------
-- Migration 007 — Curriculum Guide (program, semester offered, prerequisite)
-- Run this if you already executed db/schema.sql. Fresh installs can just
-- use the updated db/schema.sql directly (this migration is folded into it).
--------------------------------------------------------------------------

ALTER TABLE subjects ADD program VARCHAR2(20);
ALTER TABLE subjects ADD semester_offered VARCHAR2(20);
ALTER TABLE subjects ADD prerequisite_subject_id NUMBER REFERENCES subjects(subject_id) ON DELETE SET NULL;

COMMIT;
