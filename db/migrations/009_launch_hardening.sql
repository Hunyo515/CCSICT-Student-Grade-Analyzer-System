-- Existing installations: back up, apply after 008, and verify in staging first.
-- Fresh schema.sql already includes revision; do not run this on a fresh schema.
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;
ALTER TABLE teacher_subjects ADD revision NUMBER DEFAULT 0 NOT NULL;
ALTER TABLE subjects ADD CONSTRAINT ck_subject_units CHECK (units BETWEEN 1 AND 6);
ALTER TABLE grades ADD CONSTRAINT ck_grade_range CHECK (max_score > 0 AND score BETWEEN 0 AND max_score);
ALTER TABLE grade_components ADD CONSTRAINT ck_component_weight CHECK (weight_percent BETWEEN 0 AND 100);
ALTER TABLE grade_categories ADD CONSTRAINT ck_category_weight CHECK (weight_percent BETWEEN 0 AND 100);
CREATE UNIQUE INDEX uq_one_active_term ON school_terms (CASE WHEN is_active=1 THEN 1 ELSE NULL END);
CREATE UNIQUE INDEX uq_component_name ON grade_components(assignment_id, LOWER(TRIM(component_name)));
CREATE INDEX idx_enroll_assignment ON enrollments(assignment_id);
CREATE INDEX idx_components_assignment ON grade_components(assignment_id);
CREATE INDEX idx_categories_assignment ON grade_categories(assignment_id);
COMMIT;
-- If existing data violates a constraint, this script FAILS; investigate and repair
-- the records deliberately. Oracle DDL commits individually: inspect applied DDL
-- before resuming; do not blindly rerun or discard existing data.
