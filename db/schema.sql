--------------------------------------------------------------------------
-- CCT Score / Student Grade Analyzer
-- Oracle schema — Admin portal + shared foundation tables
-- Target: Oracle XE (XEPDB1) or equivalent, user "student"
--------------------------------------------------------------------------
-- Run as the "student" schema owner:
--   sqlplus student@localhost:1521/XEPDB1 @schema.sql
--------------------------------------------------------------------------

-- Fresh EMPTY schema only. Existing installations must use migrations.
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;

-- USERS  (one row per login, any role)
--------------------------------------------------------------------------
CREATE TABLE users (
    user_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR2(50)  NOT NULL UNIQUE,
    password_hash   VARCHAR2(255) NOT NULL,
    role            VARCHAR2(10)  NOT NULL CHECK (role IN ('admin','faculty','student')),
    full_name       VARCHAR2(150) NOT NULL,
    email           VARCHAR2(150),
    must_change_password NUMBER(1) DEFAULT 0 NOT NULL CHECK(must_change_password IN (0,1)),
    status          VARCHAR2(10)  DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE')),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

--------------------------------------------------------------------------
-- SCHOOL TERMS  (school year + semester, drives the term selector pills)
--------------------------------------------------------------------------
CREATE TABLE school_terms (
    term_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    school_year     VARCHAR2(20) NOT NULL,      -- e.g. '2025-2026'
    semester        VARCHAR2(20) NOT NULL,      -- e.g. '1st Semester'
    is_active       NUMBER(1) DEFAULT 0 CHECK (is_active IN (0,1)),
    enlistment_open NUMBER(1) DEFAULT 0 NOT NULL CHECK(enlistment_open IN (0,1)),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_term UNIQUE (school_year, semester)
);

--------------------------------------------------------------------------
-- SUBJECTS  (subject catalog)
--------------------------------------------------------------------------
CREATE TABLE subjects (
    catalog_folder_id NUMBER,
    subject_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_code    VARCHAR2(20)  NOT NULL,   -- e.g. CS101
    subject_name    VARCHAR2(150) NOT NULL,
    units           NUMBER(3)     NOT NULL,
    year_level      VARCHAR2(20)  NOT NULL,          -- '1st Year' .. '4th Year'
    program              VARCHAR2(20),                -- e.g. 'BSCS'; NULL = shared/general education
    semester_offered     VARCHAR2(20),                -- e.g. '1st Semester'
    prerequisite_subject_id NUMBER REFERENCES subjects(subject_id) ON DELETE SET NULL,
    lecture_units        NUMBER(3),
    lab_units            NUMBER(3),
    prerequisite_text    VARCHAR2(500),
    units_note           VARCHAR2(12),
    is_archived          NUMBER(1) DEFAULT 0 NOT NULL CHECK (is_archived IN (0,1)),
    CONSTRAINT uq_curriculum_subject UNIQUE (program, subject_code, subject_name),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

--------------------------------------------------------------------------
-- TEACHERS  (extends users where role = 'faculty')
--------------------------------------------------------------------------
CREATE TABLE teachers (
    teacher_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    program VARCHAR2(20) CHECK(program IN ('BSDSA','BSCS','BSIT','BSIS','BLIS')),
    faculty_code    VARCHAR2(20) NOT NULL UNIQUE,    -- e.g. TCH-104
    status          VARCHAR2(10) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE'))
);

--------------------------------------------------------------------------
-- STUDENTS  (extends users where role = 'student')
--------------------------------------------------------------------------
CREATE TABLE students (
    student_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    id_number       VARCHAR2(20)  NOT NULL UNIQUE,   -- e.g. CCT-22-0142
    first_name      VARCHAR2(50),
    middle_name     VARCHAR2(50),
    last_name       VARCHAR2(50),
    program         VARCHAR2(100) NOT NULL,          -- e.g. BS Computer Science
    year_level      VARCHAR2(20)  NOT NULL,
    section         VARCHAR2(20)  NOT NULL,
    age NUMBER(3) CHECK(age BETWEEN 1 AND 120),
    progress_school_year NUMBER(4),
    contact_number  VARCHAR2(30),
    sex             VARCHAR2(10) CHECK (sex IN ('MALE', 'FEMALE')),
    enrollment_type VARCHAR2(10) DEFAULT 'REGULAR' CHECK (enrollment_type IN ('REGULAR', 'IRREGULAR')),
    status          VARCHAR2(10) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','INACTIVE'))
);

--------------------------------------------------------------------------
-- TEACHER_SUBJECTS  (course-load assignment: teacher <-> subject <-> section/term)
--------------------------------------------------------------------------
CREATE TABLE teacher_subjects (
    assignment_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    teacher_id      NUMBER REFERENCES teachers(teacher_id) ON DELETE CASCADE,
    subject_id      NUMBER NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    term_id         NUMBER NOT NULL REFERENCES school_terms(term_id) ON DELETE CASCADE,
    section         VARCHAR2(20) NOT NULL,          -- e.g. BSCS 2A
    status          VARCHAR2(20) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'IN_PROGRESS', 'SUBMITTED', 'RETURNED', 'PUBLISHED')),
    aggregation     VARCHAR2(10) DEFAULT 'POINTS' NOT NULL CHECK (aggregation IN ('LEGACY','EQUAL','POINTS')),
    rounding_rule   VARCHAR2(10) DEFAULT 'UNSET' NOT NULL CHECK (rounding_rule IN ('UNSET','HALF_UP','FLOOR')),
    grading_model VARCHAR2(12) DEFAULT 'FLEXIBLE' NOT NULL CHECK(grading_model IN ('LEGACY','FLEXIBLE')),
    revision        NUMBER DEFAULT 0 NOT NULL,
    join_code       VARCHAR2(10) UNIQUE,             -- student self-enrollment code, e.g. X7K2QP
    enrollment_open VARCHAR2(1) DEFAULT 'Y' CHECK (enrollment_open IN ('Y', 'N')),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_teacher_subject_section UNIQUE (teacher_id, subject_id, section, term_id)
);

--------------------------------------------------------------------------
-- ENROLLMENTS  (student enrolled in a subject/section for a term)
--------------------------------------------------------------------------
CREATE TABLE enrollments (
    enrollment_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id      NUMBER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    assignment_id   NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id) ON DELETE CASCADE,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_enrollment UNIQUE (student_id, assignment_id)
);

--------------------------------------------------------------------------
-- GRADE_CATEGORIES  (flexible weighting tiers per assignment, e.g.
-- "Lecture" 60% + "Laboratory" 40%, or any custom split/names a teacher
-- defines. Optional — an assignment with zero rows here is in "flat" mode
-- and grade_components.weight_percent is used directly against the
-- final grade.)
--------------------------------------------------------------------------
CREATE TABLE grade_categories (
    category_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id   NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id) ON DELETE CASCADE,
    category_name   VARCHAR2(50) NOT NULL,           -- e.g. 'Lecture', 'Laboratory', 'Written Works'
    weight_percent  NUMBER(5,2) NOT NULL,             -- this category's share of the FINAL grade
    display_order   NUMBER DEFAULT 0
);

--------------------------------------------------------------------------
-- GRADE_COMPONENTS  (weighted components per assignment, e.g. Quiz 20%)
--------------------------------------------------------------------------
CREATE TABLE grade_components (
    component_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id   NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id) ON DELETE CASCADE,
    component_name  VARCHAR2(50) NOT NULL,
    weight_percent  NUMBER(5,2) NOT NULL,             -- % within its category (or, if uncategorized, % of the final grade directly)
    category_id     NUMBER REFERENCES grade_categories(category_id) ON DELETE CASCADE,
    maximum_score   NUMBER(8,2) CHECK (maximum_score>0),
    activity_date   DATE
);

--------------------------------------------------------------------------
-- GRADES  (per-student, per-component score)
--------------------------------------------------------------------------
CREATE TABLE grades (
    grade_id        NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    enrollment_id   NUMBER NOT NULL REFERENCES enrollments(enrollment_id) ON DELETE CASCADE,
    component_id    NUMBER NOT NULL REFERENCES grade_components(component_id) ON DELETE CASCADE,
    score           NUMBER(6,2),
    max_score       NUMBER(6,2) DEFAULT 100,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_grade UNIQUE (enrollment_id, component_id)
);

--------------------------------------------------------------------------
-- ACTIVITY_LOG  (drives the admin dashboard "Recent Activity" feed)
--------------------------------------------------------------------------
CREATE TABLE activity_log (
    log_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id   NUMBER REFERENCES users(user_id) ON DELETE SET NULL,
    message         VARCHAR2(300) NOT NULL,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

--------------------------------------------------------------------------
-- NOTIFICATIONS  (per-user bell in the topbar, across all 3 portals)
--------------------------------------------------------------------------
CREATE TABLE notifications (
    notification_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message         VARCHAR2(255) NOT NULL,
    link            VARCHAR2(255),
    is_read         VARCHAR2(1) DEFAULT 'N' CHECK (is_read IN ('Y', 'N')),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

--------------------------------------------------------------------------
-- Helpful indexes
--------------------------------------------------------------------------
CREATE INDEX idx_students_program   ON students(program);
CREATE INDEX idx_students_year_sec  ON students(year_level, section);
CREATE INDEX idx_subjects_year      ON subjects(year_level);
CREATE INDEX idx_teacher_subj_term  ON teacher_subjects(term_id);
CREATE UNIQUE INDEX uq_class_subject_section ON teacher_subjects(subject_id,term_id,LOWER(TRIM(section)));
CREATE INDEX idx_activity_created   ON activity_log(created_at);
CREATE INDEX idx_notif_user_unread  ON notifications(user_id, is_read);

ALTER TABLE subjects ADD CONSTRAINT ck_subject_units CHECK (units BETWEEN 1 AND 9);
ALTER TABLE grades ADD CONSTRAINT ck_grade_range CHECK (max_score > 0 AND score BETWEEN 0 AND max_score);
ALTER TABLE grade_components ADD CONSTRAINT ck_component_weight CHECK (weight_percent BETWEEN 0 AND 100);
ALTER TABLE grade_categories ADD CONSTRAINT ck_category_weight CHECK (weight_percent BETWEEN 0 AND 100);
CREATE UNIQUE INDEX uq_one_active_term ON school_terms (CASE WHEN is_active=1 THEN 1 ELSE NULL END);
CREATE UNIQUE INDEX uq_one_enlist_term ON school_terms (CASE WHEN enlistment_open=1 THEN 1 ELSE NULL END);
CREATE UNIQUE INDEX uq_component_name ON grade_components(assignment_id, LOWER(TRIM(component_name)));
CREATE INDEX idx_enroll_assignment ON enrollments(assignment_id);
CREATE INDEX idx_components_assignment ON grade_components(assignment_id);
CREATE INDEX idx_categories_assignment ON grade_categories(assignment_id);
CREATE TABLE grade_versions (
    version_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id NUMBER NOT NULL REFERENCES teacher_subjects(assignment_id),
    kind VARCHAR2(15) NOT NULL CHECK (kind IN ('RELEASE','SUBMISSION','PUBLICATION','RETURN')),
    actor_user_id NUMBER REFERENCES users(user_id) ON DELETE SET NULL,
        actor_name VARCHAR2(150),
    source_version_id NUMBER REFERENCES grade_versions(version_id),
    revision NUMBER NOT NULL, payload CLOB NOT NULL, reason VARCHAR2(500),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
CREATE INDEX idx_grade_versions_class ON grade_versions(assignment_id,kind,version_id);
CREATE TABLE academic_sections (
    section_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    term_id NUMBER NOT NULL REFERENCES school_terms(term_id),
    program VARCHAR2(20) NOT NULL, year_level VARCHAR2(20) NOT NULL,section_name VARCHAR2(20) NOT NULL,
    CONSTRAINT uq_academic_section UNIQUE(term_id,program,year_level,section_name)
);
CREATE TABLE student_term_memberships (
    membership_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id NUMBER NOT NULL REFERENCES students(student_id),
    term_id NUMBER NOT NULL REFERENCES school_terms(term_id),
    section_id NUMBER NOT NULL REFERENCES academic_sections(section_id),
    CONSTRAINT uq_student_term_member UNIQUE(student_id,term_id)
);
COMMIT;
