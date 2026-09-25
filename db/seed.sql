--------------------------------------------------------------------------
-- Seed data — matches the sample rows shown in the Figma design
-- Passwords below are the bcrypt hash of "password123" (change in prod!)
--------------------------------------------------------------------------

-- Admin user (username: admin / password: password123)
INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('admin', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'admin', 'Admin User', 'admin@cct.edu', 'ACTIVE');

-- School terms
INSERT INTO school_terms (school_year, semester, is_active) VALUES ('2025-2026', '1st Semester', 1);
INSERT INTO school_terms (school_year, semester, is_active) VALUES ('2025-2026', '2nd Semester', 0);

-- Subjects (from the Subjects Catalog screen)
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS101', 'Programming 1', 3, '1st Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS102', 'Computer Fundamentals', 3, '1st Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS201', 'Data Structures', 3, '2nd Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS202', 'Database Systems', 3, '2nd Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS203', 'Algorithms', 3, '2nd Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS301', 'Web Development', 3, '3rd Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('CS302', 'Operating Systems', 3, '3rd Year');
INSERT INTO subjects (subject_code, subject_name, units, year_level) VALUES ('MATH101', 'Statistics', 3, '1st Year');

-- Teachers (from the Faculty Members screen)
INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('e.cruz', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'faculty', 'Prof. Elena Cruz', 'e.cruz@cct.edu', 'ACTIVE');
INSERT INTO teachers (user_id, faculty_code, status)
VALUES ((SELECT user_id FROM users WHERE username='e.cruz'), 'TCH-104', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('r.santos', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'faculty', 'Prof. Ricardo Santos', 'r.santos@cct.edu', 'ACTIVE');
INSERT INTO teachers (user_id, faculty_code, status)
VALUES ((SELECT user_id FROM users WHERE username='r.santos'), 'TCH-089', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('m.bautista', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'faculty', 'Prof. Maria Bautista', 'm.bautista@cct.edu', 'ACTIVE');
INSERT INTO teachers (user_id, faculty_code, status)
VALUES ((SELECT user_id FROM users WHERE username='m.bautista'), 'TCH-112', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('a.reyes', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'faculty', 'Prof. Antonio Reyes', 'a.reyes@cct.edu', 'ACTIVE');
INSERT INTO teachers (user_id, faculty_code, status)
VALUES ((SELECT user_id FROM users WHERE username='a.reyes'), 'TCH-076', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('s.lim', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'faculty', 'Prof. Sofia Lim', 's.lim@cct.edu', 'INACTIVE');
INSERT INTO teachers (user_id, faculty_code, status)
VALUES ((SELECT user_id FROM users WHERE username='s.lim'), 'TCH-131', 'INACTIVE');

-- Teacher <-> subject assignments (course load)
INSERT INTO teacher_subjects (teacher_id, subject_id, term_id, section)
VALUES ((SELECT teacher_id FROM teachers WHERE faculty_code='TCH-104'),
        (SELECT subject_id FROM subjects WHERE subject_code='CS101'),
        (SELECT term_id FROM school_terms WHERE is_active=1), 'BSCS 1A');

INSERT INTO teacher_subjects (teacher_id, subject_id, term_id, section)
VALUES ((SELECT teacher_id FROM teachers WHERE faculty_code='TCH-104'),
        (SELECT subject_id FROM subjects WHERE subject_code='CS301'),
        (SELECT term_id FROM school_terms WHERE is_active=1), 'BSIT 3B');

-- Students (from the Students Registry screen)
INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('j.delacruz', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Juan Gabriel dela Cruz', 'j.delacruz@cct.edu', 'ACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='j.delacruz'), 'CCT-22-0142', 'BS Computer Science', '3rd Year', 'BSCS 3A', '+63 917 123 4567', 'MALE', 'REGULAR', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('m.santos', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Maria Cassandra Santos', 'm.santos@cct.edu', 'ACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='m.santos'), 'CCT-23-0891', 'BS Information Technology', '2nd Year', 'BSIT 2B', '+63 918 765 4321', 'FEMALE', 'REGULAR', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('j.bautista', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Joshua Miguel Bautista', 'j.bautista@cct.edu', 'ACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='j.bautista'), 'CCT-24-1102', 'BS Information Systems', '1st Year', 'BSIS 1A', '+63 922 456 7890', 'MALE', 'REGULAR', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('a.gonzales', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Alyssa Mae Gonzales', 'a.gonzales@cct.edu', 'INACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='a.gonzales'), 'CCT-22-0453', 'BS Computer Science', '3rd Year', 'BSCS 3B', '+63 915 987 6543', 'FEMALE', 'IRREGULAR', 'INACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('m.reyes', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Miguel Reyes', 'm.reyes@cct.edu', 'ACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='m.reyes'), 'CCT-23-0512', 'BS Information Technology', '2nd Year', 'BSIT 2B', '+63 920 111 2222', 'MALE', 'IRREGULAR', 'ACTIVE');

INSERT INTO users (username, password_hash, role, full_name, email, status)
VALUES ('c.villanueva', '$2b$12$G8kzR8n7l4b8m1s9y2eYxOQ2Zt2QeYxKQnVYb1zK8m1s9y2eYxOQ2', 'student', 'Carmela Villanueva', 'c.villanueva@cct.edu', 'ACTIVE');
INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
VALUES ((SELECT user_id FROM users WHERE username='c.villanueva'), 'CCT-24-0733', 'BS Information Systems', '1st Year', 'BSIS 1A', '+63 921 333 4444', 'FEMALE', 'REGULAR', 'ACTIVE');

INSERT INTO activity_log (actor_user_id, message) VALUES
  ((SELECT user_id FROM users WHERE username='e.cruz'), 'Teacher Cruz published Grade 10 Math grades');
INSERT INTO activity_log (actor_user_id, message) VALUES
  ((SELECT user_id FROM users WHERE username='admin'), 'Admin added new subject Web Development');
INSERT INTO activity_log (actor_user_id, message) VALUES
  ((SELECT user_id FROM users WHERE username='r.santos'), 'Teacher Santos updated BSCS 2A Data Structures scores');
INSERT INTO activity_log (actor_user_id, message) VALUES
  ((SELECT user_id FROM users WHERE username='admin'), 'Admin registered 14 new freshman student accounts');
INSERT INTO activity_log (actor_user_id, message) VALUES
  (NULL, 'System generated the Department Q2 GPA Report');

--------------------------------------------------------------------------
-- Faculty portal demo data: grade components + enrollments + sample grades
-- for TCH-104 (Prof. Elena Cruz) / CS101 Programming 1 / BSCS 1A
--------------------------------------------------------------------------

-- Grade components (Quizzes 30%, Recitation 15%, Midterm 20%, Final 13%, Projects 22%)
INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Quizzes', 30
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSCS 1A';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Recitation', 15
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSCS 1A';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Midterm Exam', 20
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSCS 1A';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Final Exam', 20
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSCS 1A';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Projects', 15
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSCS 1A';

-- Enroll the seeded students into that section
INSERT INTO enrollments (student_id, assignment_id)
SELECT s.student_id, ts.assignment_id
FROM students s
JOIN teacher_subjects ts ON ts.section = 'BSCS 1A'
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104'
  AND s.id_number IN ('CCT-22-0142', 'CCT-23-0891', 'CCT-24-1102', 'CCT-22-0453');

-- Sample scores for Juan Gabriel dela Cruz (CCT-22-0142)
INSERT INTO grades (enrollment_id, component_id, score, max_score)
SELECT e.enrollment_id, gc.component_id, 92, 100
FROM enrollments e
JOIN students s ON s.student_id = e.student_id
JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
JOIN grade_components gc ON gc.assignment_id = ts.assignment_id
WHERE s.id_number = 'CCT-22-0142' AND gc.component_name = 'Quizzes';

INSERT INTO grades (enrollment_id, component_id, score, max_score)
SELECT e.enrollment_id, gc.component_id, 89, 100
FROM enrollments e
JOIN students s ON s.student_id = e.student_id
JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
JOIN grade_components gc ON gc.assignment_id = ts.assignment_id
WHERE s.id_number = 'CCT-22-0142' AND gc.component_name = 'Midterm Exam';

-- Publish this section's grades so the Student portal (dashboard, my-rank,
-- analytics) has PUBLISHED data to show out of the box.
UPDATE teacher_subjects SET status = 'PUBLISHED'
WHERE section = 'BSCS 1A'
  AND teacher_id = (SELECT teacher_id FROM teachers WHERE faculty_code = 'TCH-104');

--------------------------------------------------------------------------
-- A second published subject (Web Development) so admin analytics has
-- more than one bar in "Class Average per Subject" and "Enrollment by
-- Subject & Sex".
--------------------------------------------------------------------------

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Quizzes', 30
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSIT 3B';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Midterm Exam', 30
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSIT 3B';

INSERT INTO grade_components (assignment_id, component_name, weight_percent)
SELECT ts.assignment_id, 'Final Project', 40
FROM teacher_subjects ts
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104' AND ts.section = 'BSIT 3B';

INSERT INTO enrollments (student_id, assignment_id)
SELECT s.student_id, ts.assignment_id
FROM students s
JOIN teacher_subjects ts ON ts.section = 'BSIT 3B'
JOIN teachers t ON t.teacher_id = ts.teacher_id
WHERE t.faculty_code = 'TCH-104'
  AND s.id_number IN ('CCT-22-0142', 'CCT-23-0891', 'CCT-23-0512');

INSERT INTO grades (enrollment_id, component_id, score, max_score)
SELECT e.enrollment_id, gc.component_id, 88, 100
FROM enrollments e
JOIN students s ON s.student_id = e.student_id
JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
JOIN grade_components gc ON gc.assignment_id = ts.assignment_id
WHERE s.id_number = 'CCT-22-0142' AND ts.section = 'BSIT 3B' AND gc.component_name = 'Quizzes';

INSERT INTO grades (enrollment_id, component_id, score, max_score)
SELECT e.enrollment_id, gc.component_id, 90, 100
FROM enrollments e
JOIN students s ON s.student_id = e.student_id
JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
JOIN grade_components gc ON gc.assignment_id = ts.assignment_id
WHERE s.id_number = 'CCT-23-0891' AND ts.section = 'BSIT 3B' AND gc.component_name = 'Quizzes';

INSERT INTO grades (enrollment_id, component_id, score, max_score)
SELECT e.enrollment_id, gc.component_id, 78, 100
FROM enrollments e
JOIN students s ON s.student_id = e.student_id
JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
JOIN grade_components gc ON gc.assignment_id = ts.assignment_id
WHERE s.id_number = 'CCT-23-0512' AND ts.section = 'BSIT 3B' AND gc.component_name = 'Midterm Exam';

UPDATE teacher_subjects SET status = 'PUBLISHED'
WHERE section = 'BSIT 3B'
  AND teacher_id = (SELECT teacher_id FROM teachers WHERE faculty_code = 'TCH-104');

COMMIT;

-- NOTE: The password hashes above are placeholders (not a real bcrypt hash
-- of "password123"). Run `python scripts/reset_password.py admin password123`
-- after seeding to set real, correctly-hashed passwords before using login.
