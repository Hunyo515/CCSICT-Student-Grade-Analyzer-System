--------------------------------------------------------------------------
-- CCT Score / Student Grade Analyzer
-- Oracle schema — Admin portal + shared foundation tables
-- Target: Oracle XE (XEPDB1) or equivalent, user "student"
--------------------------------------------------------------------------
-- Run as the "student" schema owner:
--   sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @schema.sql
--------------------------------------------------------------------------

-- Drop order respects FKs (ignore errors on first run if objects absent)
BEGIN EXECUTE IMMEDIATE 'DROP TABLE activity_log CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE grades CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE grade_components CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE teacher_subjects CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE enrollments CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE students CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE teachers CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE subjects CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE school_terms CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE users CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

--------------------------------------------------------------------------
-- USERS  (one row per login, any role)
--------------------------------------------------------------------------
CREATE TABLE users (
    user_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR2(50)  NOT NULL UNIQUE,
    password_hash   VARCHAR2(255) NOT NULL,
    role            VARCHAR2(10)  NOT NULL CHECK (role IN ('admin','faculty','student')),
    full_name       VARCHAR2(150) NOT NULL,
    email           VARCHAR2(150),
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
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_term UNIQUE (school_year, semester)
);

--------------------------------------------------------------------------
-- SUBJECTS  (subject catalog)
--------------------------------------------------------------------------
CREATE TABLE subjects (
    subject_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_code    VARCHAR2(20)  NOT NULL UNIQUE,   -- e.g. CS101
    subject_name    VARCHAR2(150) NOT NULL,
    units           NUMBER(3)     NOT NULL,
    year_level      VARCHAR2(20)  NOT NULL,          -- '1st Year' .. '4th Year'
    program              VARCHAR2(20),                -- e.g. 'BSCS'; NULL = shared/general education
    semester_offered     VARCHAR2(20),                -- e.g. '1st Semester'
    prerequisite_subject_id NUMBER REFERENCES subjects(subject_id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

--------------------------------------------------------------------------
-- TEACHERS  (extends users where role = 'faculty')
--------------------------------------------------------------------------
CREATE TABLE teachers (
    teacher_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
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
    program         VARCHAR2(100) NOT NULL,          -- e.g. BS Computer Science
    year_level      VARCHAR2(20)  NOT NULL,
    section         VARCHAR2(20)  NOT NULL,
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
    teacher_id      NUMBER NOT NULL REFERENCES teachers(teacher_id) ON DELETE CASCADE,
    subject_id      NUMBER NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    term_id         NUMBER NOT NULL REFERENCES school_terms(term_id) ON DELETE CASCADE,
    section         VARCHAR2(20) NOT NULL,          -- e.g. BSCS 2A
    status          VARCHAR2(20) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'IN_PROGRESS', 'PUBLISHED')),
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
    category_id     NUMBER REFERENCES grade_categories(category_id) ON DELETE CASCADE
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
CREATE INDEX idx_activity_created   ON activity_log(created_at);
CREATE INDEX idx_notif_user_unread  ON notifications(user_id, is_read);

COMMIT;
