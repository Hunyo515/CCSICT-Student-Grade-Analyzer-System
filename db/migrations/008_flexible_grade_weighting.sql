--------------------------------------------------------------------------
-- Migration 008 — Flexible grade weighting categories
--
-- Supersedes the fixed Lecture/Laboratory split added in migration 005.
-- Faculty can now define ANY number of categories with ANY names and
-- weights (e.g. "Lecture" 60% + "Laboratory" 40%, or "Written Works" 30%
-- + "Performance Tasks" 40% + "Exams" 30%), each summing its own
-- components to 100% internally.
--
-- Requires migration 005 to have already been run (uses
-- teacher_subjects.lecture_split/lab_split and
-- grade_components.category to backfill data before dropping them).
-- Run this if you already executed db/schema.sql. Fresh installs can
-- just use the updated db/schema.sql directly (this migration is
-- folded into it).
--------------------------------------------------------------------------

CREATE TABLE grade_categories (
    category_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id   NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id) ON DELETE CASCADE,
    category_name   VARCHAR2(50) NOT NULL,
    weight_percent  NUMBER(5,2) NOT NULL,
    display_order   NUMBER DEFAULT 0
);

ALTER TABLE grade_components ADD category_id NUMBER REFERENCES grade_categories(category_id) ON DELETE CASCADE;

-- Backfill: turn each assignment's old lecture_split/lab_split + per-component
-- LECTURE/LAB tag into real grade_categories rows, and point existing
-- components at the new category rows. Assignments that never touched the
-- old Lecture/Lab feature (no components, or default 100/0 split with
-- nothing tagged LAB) simply get a single "Lecture" category — no visible
-- change to their computed grades.
DECLARE
    v_lecture_id NUMBER;
    v_lab_id     NUMBER;
    v_lab_count  NUMBER;
    v_component_count NUMBER;
BEGIN
    FOR ts IN (SELECT assignment_id, lecture_split, lab_split FROM teacher_subjects) LOOP
        SELECT COUNT(*) INTO v_lab_count
        FROM grade_components
        WHERE assignment_id = ts.assignment_id AND category = 'LAB';

        -- Only create categories for assignments that actually have components.
        SELECT COUNT(*) INTO v_component_count
        FROM grade_components
        WHERE assignment_id = ts.assignment_id;

        IF v_component_count > 0 THEN
            INSERT INTO grade_categories (assignment_id, category_name, weight_percent, display_order)
            VALUES (ts.assignment_id, 'Lecture', NVL(ts.lecture_split, 100), 1)
            RETURNING category_id INTO v_lecture_id;

            UPDATE grade_components
            SET category_id = v_lecture_id
            WHERE assignment_id = ts.assignment_id AND (category IS NULL OR category = 'LECTURE');

            IF v_lab_count > 0 THEN
                INSERT INTO grade_categories (assignment_id, category_name, weight_percent, display_order)
                VALUES (ts.assignment_id, 'Laboratory', NVL(ts.lab_split, 0), 2)
                RETURNING category_id INTO v_lab_id;

                UPDATE grade_components
                SET category_id = v_lab_id
                WHERE assignment_id = ts.assignment_id AND category = 'LAB';
            END IF;
        END IF;
    END LOOP;
    COMMIT;
END;
/

-- The old columns are now fully superseded. Drop them so there's a single
-- source of truth for grade weighting going forward.
ALTER TABLE grade_components DROP COLUMN category;
ALTER TABLE teacher_subjects DROP COLUMN lecture_split;
ALTER TABLE teacher_subjects DROP COLUMN lab_split;

COMMIT;
