import math

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import hash_password, login_required
from ..db import execute, execute_returning_id, query_all, query_one
from ..grading import compute_weighted_total
from ..notifications import notify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def active_term():
    term = query_one("SELECT term_id, school_year, semester FROM school_terms WHERE is_active = 1")
    if not term:
        term = query_one(
            "SELECT term_id, school_year, semester FROM school_terms ORDER BY term_id DESC FETCH FIRST 1 ROWS ONLY"
        )
    return term


def paginate(total_count, page, page_size=PAGE_SIZE):
    total_pages = max(1, math.ceil(total_count / page_size))
    page = min(max(1, page), total_pages)
    offset = (page - 1) * page_size
    return page, total_pages, offset


def log_activity(message):
    execute(
        "INSERT INTO activity_log (actor_user_id, message) VALUES (:user_id, :msg)",
        {"user_id": session.get("user_id"), "msg": message},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/dashboard")
@login_required("admin")
def dashboard():
    term = active_term()

    stats = {
        "total_students": query_one("SELECT COUNT(*) AS n FROM students WHERE status='ACTIVE'")["n"],
        "total_teachers": query_one("SELECT COUNT(*) AS n FROM teachers WHERE status='ACTIVE'")["n"],
        "total_subjects": query_one("SELECT COUNT(*) AS n FROM subjects")["n"],
    }

    recent_activity = query_all(
        """
        SELECT message, created_at
        FROM activity_log
        ORDER BY created_at DESC
        FETCH FIRST 6 ROWS ONLY
        """
    )

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_activity=recent_activity,
        term=term,
    )


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

@admin_bp.route("/subjects")
@login_required("admin")
def subjects():
    term = active_term()
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))

    where = ""
    params = {}
    if q:
        where = "WHERE LOWER(subject_code) LIKE :q OR LOWER(subject_name) LIKE :q"
        params["q"] = f"%{q.lower()}%"

    total = query_one(f"SELECT COUNT(*) AS n FROM subjects {where}", params)["n"]
    page, total_pages, offset = paginate(total, page)

    rows = query_all(
        f"""
        SELECT subject_id, subject_code, subject_name, units, year_level
        FROM subjects
        {where}
        ORDER BY subject_code
        OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY
        """,
        params,
    )

    return render_template(
        "admin/subjects.html",
        term=term,
        subjects=rows,
        q=q,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@admin_bp.route("/subjects/add", methods=["POST"])
@login_required("admin")
def add_subject():
    code = request.form.get("subject_code", "").strip().upper()
    name = request.form.get("subject_name", "").strip()
    units = request.form.get("units", "3").strip()
    year_level = request.form.get("year_level", "1st Year").strip()

    if not code or not name:
        flash("Subject code and name are required.", "error")
        return redirect(url_for("admin.subjects"))

    existing = query_one("SELECT subject_id FROM subjects WHERE subject_code = :c", {"c": code})
    if existing:
        flash(f"Subject code {code} already exists.", "error")
        return redirect(url_for("admin.subjects"))

    execute(
        """
        INSERT INTO subjects (subject_code, subject_name, units, year_level)
        VALUES (:code, :name, :units, :year_level)
        """,
        {"code": code, "name": name, "units": units, "year_level": year_level},
    )
    log_activity(f"Admin added new subject {name}")
    flash(f"Subject {code} added.", "success")
    return redirect(url_for("admin.subjects"))


@admin_bp.route("/subjects/<int:subject_id>/edit", methods=["POST"])
@login_required("admin")
def edit_subject(subject_id):
    name = request.form.get("subject_name", "").strip()
    units = request.form.get("units", "3").strip()
    year_level = request.form.get("year_level", "1st Year").strip()

    execute(
        """
        UPDATE subjects
        SET subject_name = :name, units = :units, year_level = :year_level, updated_at = SYSTIMESTAMP
        WHERE subject_id = :id
        """,
        {"name": name, "units": units, "year_level": year_level, "id": subject_id},
    )
    flash("Subject updated.", "success")
    return redirect(url_for("admin.subjects"))


@admin_bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required("admin")
def delete_subject(subject_id):
    execute("DELETE FROM subjects WHERE subject_id = :id", {"id": subject_id})
    flash("Subject deleted.", "success")
    return redirect(url_for("admin.subjects"))


PROGRAMS = ["BSCS", "BSIT", "BSIS", "BSDSA", "BLIS"]
YEAR_ORDER = ["1st Year", "2nd Year", "3rd Year", "4th Year"]


@admin_bp.route("/subjects/curriculum")
@login_required("admin")
def curriculum_guide():
    term = active_term()
    program = request.args.get("program", "BSCS").upper()
    if program not in PROGRAMS:
        program = "BSCS"

    rows = query_all(
        """
        SELECT s.subject_id, s.subject_code, s.subject_name, s.units, s.year_level,
               s.program, s.semester_offered, s.prerequisite_subject_id,
               p.subject_code AS prerequisite_code
        FROM subjects s
        LEFT JOIN subjects p ON p.subject_id = s.prerequisite_subject_id
        WHERE s.program = :program OR s.program IS NULL
        ORDER BY s.year_level, s.subject_code
        """,
        {"program": program},
    )
    grouped = {yl: [] for yl in YEAR_ORDER}
    for r in rows:
        grouped.setdefault(r["year_level"], []).append(r)

    all_subjects = query_all(
        "SELECT subject_id, subject_code, subject_name FROM subjects ORDER BY subject_code"
    )

    return render_template(
        "admin/curriculum_guide.html",
        term=term,
        program=program,
        programs=PROGRAMS,
        year_levels=YEAR_ORDER,
        grouped=grouped,
        year_order=[yl for yl in YEAR_ORDER if grouped.get(yl)],
        all_subjects=all_subjects,
    )


@admin_bp.route("/subjects/curriculum/add", methods=["POST"])
@login_required("admin")
def add_curriculum_subject():
    program = request.form.get("program", "BSCS").strip().upper()
    code = request.form.get("subject_code", "").strip().upper()
    name = request.form.get("subject_name", "").strip()
    units = request.form.get("units", "3").strip()
    year_level = request.form.get("year_level", "1st Year").strip()
    semester_offered = request.form.get("semester_offered", "").strip() or None
    prerequisite_subject_id = request.form.get("prerequisite_subject_id", type=int)
    shared = request.form.get("shared") == "on"

    if not code or not name:
        flash("Subject code and name are required.", "error")
        return redirect(url_for("admin.curriculum_guide", program=program))

    existing = query_one("SELECT subject_id FROM subjects WHERE subject_code = :c", {"c": code})
    if existing:
        flash(f"Subject code {code} already exists.", "error")
        return redirect(url_for("admin.curriculum_guide", program=program))

    execute(
        """
        INSERT INTO subjects (subject_code, subject_name, units, year_level, program, semester_offered, prerequisite_subject_id)
        VALUES (:code, :name, :units, :year_level, :program, :semester_offered, :prereq)
        """,
        {
            "code": code, "name": name, "units": units, "year_level": year_level,
            "program": None if shared else program,
            "semester_offered": semester_offered,
            "prereq": prerequisite_subject_id,
        },
    )
    log_activity(f"Admin added {code} to the {program} curriculum guide")
    flash(f"{code} added to the curriculum guide.", "success")
    return redirect(url_for("admin.curriculum_guide", program=program))


@admin_bp.route("/subjects/curriculum/<int:subject_id>/edit", methods=["POST"])
@login_required("admin")
def edit_curriculum_subject(subject_id):
    program = request.form.get("program", "BSCS").strip().upper()
    name = request.form.get("subject_name", "").strip()
    units = request.form.get("units", "3").strip()
    year_level = request.form.get("year_level", "1st Year").strip()
    semester_offered = request.form.get("semester_offered", "").strip() or None
    prerequisite_subject_id = request.form.get("prerequisite_subject_id", type=int)
    shared = request.form.get("shared") == "on"

    if prerequisite_subject_id == subject_id:
        flash("A subject can't be its own prerequisite.", "error")
        return redirect(url_for("admin.curriculum_guide", program=program))

    execute(
        """
        UPDATE subjects
        SET subject_name = :name, units = :units, year_level = :year_level,
            program = :program, semester_offered = :semester_offered,
            prerequisite_subject_id = :prereq, updated_at = SYSTIMESTAMP
        WHERE subject_id = :id
        """,
        {
            "name": name, "units": units, "year_level": year_level,
            "program": None if shared else program,
            "semester_offered": semester_offered,
            "prereq": prerequisite_subject_id, "id": subject_id,
        },
    )
    flash("Curriculum entry updated.", "success")
    return redirect(url_for("admin.curriculum_guide", program=program))


@admin_bp.route("/subjects/curriculum/<int:subject_id>/delete", methods=["POST"])
@login_required("admin")
def delete_curriculum_subject(subject_id):
    program = request.form.get("program", "BSCS").strip().upper()
    try:
        execute("DELETE FROM subjects WHERE subject_id = :id", {"id": subject_id})
        flash("Curriculum entry deleted.", "success")
    except Exception:
        flash("Can't delete this subject — it's already in use by a class section or grade record.", "error")
    return redirect(url_for("admin.curriculum_guide", program=program))


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

@admin_bp.route("/teachers")
@login_required("admin")
def teachers():
    term = active_term()
    q = request.args.get("q", "").strip()

    where = ""
    params = {"term_id": term["term_id"] if term else 0}
    if q:
        where = "WHERE LOWER(u.full_name) LIKE :q"
        params["q"] = f"%{q.lower()}%"

    rows = query_all(
        f"""
        SELECT
            t.teacher_id,
            t.faculty_code,
            u.full_name,
            u.email,
            t.status,
            LISTAGG(s.subject_name, ', ') WITHIN GROUP (ORDER BY s.subject_name) AS assigned_subjects
        FROM teachers t
        JOIN users u ON u.user_id = t.user_id
        LEFT JOIN teacher_subjects ts ON ts.teacher_id = t.teacher_id AND ts.term_id = :term_id
        LEFT JOIN subjects s ON s.subject_id = ts.subject_id
        {where}
        GROUP BY t.teacher_id, t.faculty_code, u.full_name, u.email, t.status
        ORDER BY u.full_name
        """,
        params,
    )

    all_subjects = query_all("SELECT subject_id, subject_name FROM subjects ORDER BY subject_name")
    all_teachers = query_all(
        """
        SELECT t.teacher_id, u.full_name
        FROM teachers t JOIN users u ON u.user_id = t.user_id
        ORDER BY u.full_name
        """
    )

    return render_template(
        "admin/teachers.html",
        term=term,
        teachers=rows,
        q=q,
        all_subjects=all_subjects,
        all_teachers=all_teachers,
    )


@admin_bp.route("/teachers/add", methods=["POST"])
@login_required("admin")
def add_teacher():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    faculty_code = request.form.get("faculty_code", "").strip().upper()
    username = request.form.get("username", "").strip() or (email.split("@")[0] if email else "")
    temp_password = request.form.get("password", "").strip() or "changeme123"

    if not full_name or not email or not faculty_code or not username:
        flash("Full name, email, faculty code, and username are required.", "error")
        return redirect(url_for("admin.teachers"))

    if query_one("SELECT user_id FROM users WHERE username = :u", {"u": username}):
        flash(f"Username {username} is already taken.", "error")
        return redirect(url_for("admin.teachers"))

    user_id = execute_returning_id(
        """
        INSERT INTO users (username, password_hash, role, full_name, email, status)
        VALUES (:username, :pw, 'faculty', :full_name, :email, 'ACTIVE')
        RETURNING user_id INTO :out_id
        """,
        {
            "username": username,
            "pw": hash_password(temp_password),
            "full_name": full_name,
            "email": email,
        },
    )
    execute(
        "INSERT INTO teachers (user_id, faculty_code, status) VALUES (:user_id, :code, 'ACTIVE')",
        {"user_id": user_id, "code": faculty_code},
    )
    log_activity(f"Admin added new faculty member {full_name}")
    flash(f"Teacher {full_name} added (temp password: {temp_password}).", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:teacher_id>/edit", methods=["POST"])
@login_required("admin")
def edit_teacher(teacher_id):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "ACTIVE")

    row = query_one("SELECT user_id FROM teachers WHERE teacher_id = :id", {"id": teacher_id})
    if not row:
        flash("Teacher not found.", "error")
        return redirect(url_for("admin.teachers"))

    execute(
        "UPDATE users SET full_name = :name, email = :email, updated_at = SYSTIMESTAMP WHERE user_id = :user_id",
        {"name": full_name, "email": email, "user_id": row["user_id"]},
    )
    new_password = request.form.get("new_password", "").strip()
    if new_password:
        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": row["user_id"]},
        )
        notify(row["user_id"], "Your password was reset by an administrator.", link=url_for("auth.select_role"))
    execute("UPDATE teachers SET status = :status WHERE teacher_id = :id", {"status": status, "id": teacher_id})
    flash("Teacher updated.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required("admin")
def delete_teacher(teacher_id):
    row = query_one("SELECT user_id FROM teachers WHERE teacher_id = :id", {"id": teacher_id})
    if row:
        execute("DELETE FROM users WHERE user_id = :user_id", {"user_id": row["user_id"]})  # cascades to teachers
    flash("Teacher removed.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/assign", methods=["POST"])
@login_required("admin")
def assign_subject():
    term = active_term()
    teacher_id = request.form.get("teacher_id")
    subject_id = request.form.get("subject_id")
    section = request.form.get("section", "").strip()

    if not teacher_id or not subject_id or not section:
        flash("Teacher, subject, and section are required.", "error")
        return redirect(url_for("admin.teachers"))

    existing = query_one(
        """
        SELECT assignment_id FROM teacher_subjects
        WHERE teacher_id = :tid AND subject_id = :sid AND section = :sec AND term_id = :term_id
        """,
        {"tid": teacher_id, "sid": subject_id, "sec": section, "term_id": term["term_id"]},
    )
    if existing:
        flash("That assignment already exists.", "error")
        return redirect(url_for("admin.teachers"))

    execute(
        """
        INSERT INTO teacher_subjects (teacher_id, subject_id, term_id, section)
        VALUES (:tid, :sid, :term_id, :sec)
        """,
        {"tid": teacher_id, "sid": subject_id, "term_id": term["term_id"], "sec": section},
    )
    flash("Course load assigned.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/assignment/<int:assignment_id>/remove", methods=["POST"])
@login_required("admin")
def remove_assignment(assignment_id):
    execute("DELETE FROM teacher_subjects WHERE assignment_id = :id", {"id": assignment_id})
    flash("Assignment removed.", "success")
    return redirect(url_for("admin.teachers"))


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@admin_bp.route("/students")
@login_required("admin")
def students():
    term = active_term()
    q = request.args.get("q", "").strip()
    year_level = request.args.get("year_level", "").strip()
    section = request.args.get("section", "").strip()
    program = request.args.get("program", "").strip()
    page = int(request.args.get("page", 1))

    filters = []
    params = {}
    if q:
        filters.append("(LOWER(u.full_name) LIKE :q OR LOWER(s.id_number) LIKE :q OR LOWER(s.program) LIKE :q)")
        params["q"] = f"%{q.lower()}%"
    if year_level:
        filters.append("s.year_level = :year_level")
        params["year_level"] = year_level
    if section:
        filters.append("s.section = :section")
        params["section"] = section
    if program:
        filters.append("s.program = :program")
        params["program"] = program

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = query_one(
        f"""
        SELECT COUNT(*) AS n
        FROM students s JOIN users u ON u.user_id = s.user_id
        {where}
        """,
        params,
    )["n"]
    page, total_pages, offset = paginate(total, page)

    rows = query_all(
        f"""
        SELECT s.student_id, s.id_number, u.full_name, s.program, s.year_level,
               s.section, s.contact_number, s.sex, s.enrollment_type, s.status
        FROM students s JOIN users u ON u.user_id = s.user_id
        {where}
        ORDER BY u.full_name
        OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY
        """,
        params,
    )

    year_levels = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
    programs = query_all("SELECT DISTINCT program FROM students ORDER BY program")
    sections = query_all("SELECT DISTINCT section FROM students ORDER BY section")

    return render_template(
        "admin/students.html",
        term=term,
        students=rows,
        q=q,
        year_level=year_level,
        section=section,
        program=program,
        year_levels=year_levels,
        programs=[p["program"] for p in programs],
        sections=[s["section"] for s in sections],
        page=page,
        total_pages=total_pages,
        total=total,
    )


@admin_bp.route("/students/add", methods=["POST"])
@login_required("admin")
def add_student():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    full_name = f"{first_name} {last_name}".strip()
    email = request.form.get("email", "").strip()
    id_number = request.form.get("id_number", "").strip().upper()
    program = request.form.get("program", "").strip()
    year_level = request.form.get("year_level", "").strip()
    section = request.form.get("section", "").strip()
    contact_number = request.form.get("contact_number", "").strip()
    sex = request.form.get("sex", "").strip() or None
    enrollment_type = request.form.get("enrollment_type", "REGULAR").strip() or "REGULAR"
    username = request.form.get("username", "").strip() or id_number.lower()
    temp_password = request.form.get("password", "").strip() or "changeme123"

    if not all([first_name, last_name, id_number, program, year_level, section]):
        flash("First name, last name, ID number, program, year level, and section are required.", "error")
        return redirect(url_for("admin.students"))

    if query_one("SELECT student_id FROM students WHERE id_number = :i", {"i": id_number}):
        flash(f"ID number {id_number} already exists.", "error")
        return redirect(url_for("admin.students"))

    user_id = execute_returning_id(
        """
        INSERT INTO users (username, password_hash, role, full_name, email, status)
        VALUES (:username, :pw, 'student', :full_name, :email, 'ACTIVE')
        RETURNING user_id INTO :out_id
        """,
        {
            "username": username,
            "pw": hash_password(temp_password),
            "full_name": full_name,
            "email": email,
        },
    )
    execute(
        """
        INSERT INTO students (user_id, id_number, program, year_level, section, contact_number, sex, enrollment_type, status)
        VALUES (:user_id, :id_number, :program, :year_level, :section, :contact, :sex, :enrollment_type, 'ACTIVE')
        """,
        {
            "user_id": user_id,
            "id_number": id_number,
            "program": program,
            "year_level": year_level,
            "section": section,
            "contact": contact_number,
            "sex": sex,
            "enrollment_type": enrollment_type,
        },
    )
    log_activity(f"Admin registered new student {full_name} ({id_number})")
    flash(f"Student {full_name} added (temp password: {temp_password}).", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/edit", methods=["POST"])
@login_required("admin")
def edit_student(student_id):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    program = request.form.get("program", "").strip()
    year_level = request.form.get("year_level", "").strip()
    section = request.form.get("section", "").strip()
    contact_number = request.form.get("contact_number", "").strip()
    status = request.form.get("status", "ACTIVE")
    sex = request.form.get("sex", "").strip() or None
    enrollment_type = request.form.get("enrollment_type", "REGULAR").strip() or "REGULAR"

    row = query_one("SELECT user_id FROM students WHERE student_id = :id", {"id": student_id})
    if not row:
        flash("Student not found.", "error")
        return redirect(url_for("admin.students"))

    execute(
        "UPDATE users SET full_name = :name, email = :email, updated_at = SYSTIMESTAMP WHERE user_id = :user_id",
        {"name": full_name, "email": email, "user_id": row["user_id"]},
    )
    new_password = request.form.get("new_password", "").strip()
    if new_password:
        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": row["user_id"]},
        )
        notify(row["user_id"], "Your password was reset by an administrator.", link=url_for("auth.select_role"))
    execute(
        """
        UPDATE students
        SET program = :program, year_level = :year_level, section = :section,
            contact_number = :contact, status = :status, sex = :sex, enrollment_type = :enrollment_type
        WHERE student_id = :id
        """,
        {
            "program": program,
            "year_level": year_level,
            "section": section,
            "contact": contact_number,
            "status": status,
            "sex": sex,
            "enrollment_type": enrollment_type,
            "id": student_id,
        },
    )
    flash("Student updated.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required("admin")
def delete_student(student_id):
    row = query_one("SELECT user_id FROM students WHERE student_id = :id", {"id": student_id})
    if row:
        execute("DELETE FROM users WHERE user_id = :user_id", {"user_id": row["user_id"]})  # cascades to students
    flash("Student removed.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/assign", methods=["GET", "POST"])
@login_required("admin")
def assign_student_to_section():
    term = active_term()
    terms = query_all("SELECT term_id, school_year, semester FROM school_terms ORDER BY term_id DESC")
    subjects = query_all("SELECT subject_id, subject_code, subject_name FROM subjects ORDER BY subject_code")
    students = query_all(
        """
        SELECT s.student_id, s.id_number, u.full_name, s.program
        FROM students s JOIN users u ON u.user_id = s.user_id
        WHERE s.status = 'ACTIVE'
        ORDER BY u.full_name
        """
    )
    assignments = query_all(
        """
        SELECT ts.assignment_id, ts.subject_id, ts.term_id, ts.section, u.full_name AS teacher_name
        FROM teacher_subjects ts
        JOIN teachers t ON t.teacher_id = ts.teacher_id
        JOIN users u ON u.user_id = t.user_id
        ORDER BY ts.section
        """
    )

    if request.method == "POST":
        student_id = request.form.get("student_id")
        assignment_id = request.form.get("assignment_id")

        if not student_id or not assignment_id:
            flash("Select a student and a section allocation.", "error")
            return redirect(url_for("admin.assign_student_to_section"))

        existing = query_one(
            "SELECT enrollment_id FROM enrollments WHERE student_id = :sid AND assignment_id = :aid",
            {"sid": student_id, "aid": assignment_id},
        )
        if existing:
            flash("That student is already enrolled in this section.", "error")
            return redirect(url_for("admin.assign_student_to_section"))

        execute(
            "INSERT INTO enrollments (student_id, assignment_id) VALUES (:sid, :aid)",
            {"sid": student_id, "aid": assignment_id},
        )

        detail = query_one(
            """
            SELECT su.user_id AS student_user_id, su.full_name AS student_name,
                   tu.user_id AS teacher_user_id, subj.subject_name, ts.section
            FROM enrollments e
            JOIN students s ON s.student_id = e.student_id
            JOIN users su ON su.user_id = s.user_id
            JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
            JOIN subjects subj ON subj.subject_id = ts.subject_id
            JOIN teachers t ON t.teacher_id = ts.teacher_id
            JOIN users tu ON tu.user_id = t.user_id
            WHERE e.student_id = :sid AND e.assignment_id = :aid
            """,
            {"sid": student_id, "aid": assignment_id},
        )
        if detail:
            notify(
                detail["student_user_id"],
                f"You've been enrolled in {detail['subject_name']} ({detail['section']}) by the admin.",
                link=url_for("student.dashboard"),
            )
            notify(
                detail["teacher_user_id"],
                f"{detail['student_name']} was added to {detail['subject_name']} ({detail['section']}) by the admin.",
                link=url_for("faculty.section_detail", assignment_id=assignment_id),
            )

        log_activity("Admin manually assigned a student to a class section")
        flash("Student assigned to section.", "success")
        return redirect(url_for("admin.students"))

    return render_template(
        "admin/assign_student.html",
        term=term,
        terms=terms,
        subjects=subjects,
        students=students,
        assignments=assignments,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@admin_bp.route("/settings")
@login_required("admin")
def settings():
    terms = query_all("SELECT term_id, school_year, semester, is_active FROM school_terms ORDER BY term_id DESC")
    active = next((t for t in terms if t["is_active"]), None)
    active_id = active["term_id"] if active else None
    for t in terms:
        if t["is_active"]:
            t["state"] = "active"
        elif active_id is not None and t["term_id"] > active_id:
            t["state"] = "upcoming"
        else:
            t["state"] = "completed"
    admin_user = query_one(
        "SELECT username, full_name, email FROM users WHERE user_id = :user_id",
        {"user_id": session["user_id"]},
    )
    return render_template("admin/settings.html", terms=terms, admin_user=admin_user, term=active)


@admin_bp.route("/settings/terms/add", methods=["POST"])
@login_required("admin")
def add_term():
    school_year = request.form.get("school_year", "").strip()
    semester = request.form.get("semester", "").strip()

    if not school_year or not semester:
        flash("School year and semester are required.", "error")
        return redirect(url_for("admin.settings"))

    if query_one(
        "SELECT term_id FROM school_terms WHERE school_year = :y AND semester = :s",
        {"y": school_year, "s": semester},
    ):
        flash("That term already exists.", "error")
        return redirect(url_for("admin.settings"))

    execute(
        "INSERT INTO school_terms (school_year, semester, is_active) VALUES (:y, :s, 0)",
        {"y": school_year, "s": semester},
    )
    flash("Term added.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/terms/<int:term_id>/activate", methods=["POST"])
@login_required("admin")
def activate_term(term_id):
    execute("UPDATE school_terms SET is_active = 0")
    execute("UPDATE school_terms SET is_active = 1 WHERE term_id = :id", {"id": term_id})
    flash("Active term updated.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/profile", methods=["POST"])
@login_required("admin")
def update_profile():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    new_password = request.form.get("new_password", "").strip()

    execute(
        "UPDATE users SET full_name = :name, email = :email, updated_at = SYSTIMESTAMP WHERE user_id = :user_id",
        {"name": full_name, "email": email, "user_id": session["user_id"]},
    )
    if new_password:
        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": session["user_id"]},
        )
    session["full_name"] = full_name
    flash("Profile updated.", "success")
    return redirect(url_for("admin.settings"))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _subject_class_averages(term_id):
    """Average weighted grade per subject, across all PUBLISHED sections/students."""
    subjects = query_all(
        """
        SELECT DISTINCT s.subject_id, s.subject_name
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        WHERE ts.term_id = :term_id AND ts.status = 'PUBLISHED'
        ORDER BY s.subject_name
        """,
        {"term_id": term_id},
    )

    results = []
    for subj in subjects:
        assignments = query_all(
            """
            SELECT assignment_id FROM teacher_subjects
            WHERE subject_id = :sid AND term_id = :term_id AND status = 'PUBLISHED'
            """,
            {"sid": subj["subject_id"], "term_id": term_id},
        )
        totals = []
        for a in assignments:
            components = query_all(
                "SELECT component_id, weight_percent, category_id FROM grade_components WHERE assignment_id = :id",
                {"id": a["assignment_id"]},
            )
            if not components:
                continue
            categories = query_all(
                "SELECT category_id, weight_percent FROM grade_categories WHERE assignment_id = :id",
                {"id": a["assignment_id"]},
            )
            splits = {c["category_id"]: c["weight_percent"] for c in categories}
            enrollments = query_all(
                "SELECT enrollment_id FROM enrollments WHERE assignment_id = :id",
                {"id": a["assignment_id"]},
            )
            for e in enrollments:
                score_rows = query_all(
                    "SELECT component_id, score, max_score FROM grades WHERE enrollment_id = :id",
                    {"id": e["enrollment_id"]},
                )
                scores = {r["component_id"]: (r["score"], r["max_score"]) for r in score_rows}
                totals.append(compute_weighted_total(scores, components, splits))

        if totals:
            results.append({
                "subject_name": subj["subject_name"],
                "avg": round(sum(totals) / len(totals), 1),
            })
    return results


@admin_bp.route("/analytics")
@login_required("admin")
def analytics():
    term = active_term()
    term_id = term["term_id"] if term else 0

    # 1. Enrollment by Program
    by_program = query_all(
        """
        SELECT program, COUNT(*) AS n
        FROM students
        WHERE status = 'ACTIVE'
        GROUP BY program
        ORDER BY n DESC
        """
    )

    # 2. Enrollment by Year Level
    by_year_level = query_all(
        """
        SELECT year_level, COUNT(*) AS n
        FROM students
        WHERE status = 'ACTIVE'
        GROUP BY year_level
        ORDER BY year_level
        """
    )

    # 3. Enrollment by Subject & Sex
    by_subject_sex = query_all(
        """
        SELECT s.subject_name,
               SUM(CASE WHEN st.sex = 'MALE' THEN 1 ELSE 0 END) AS male_count,
               SUM(CASE WHEN st.sex = 'FEMALE' THEN 1 ELSE 0 END) AS female_count
        FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
        JOIN subjects s ON s.subject_id = ts.subject_id
        JOIN students st ON st.student_id = e.student_id
        WHERE ts.term_id = :term_id
        GROUP BY s.subject_name
        ORDER BY s.subject_name
        """,
        {"term_id": term_id},
    )

    # 4. Student Distribution by Sex
    by_sex = query_all(
        """
        SELECT sex, COUNT(*) AS n
        FROM students
        WHERE status = 'ACTIVE' AND sex IS NOT NULL
        GROUP BY sex
        """
    )
    male_count = next((r["n"] for r in by_sex if r["sex"] == "MALE"), 0)
    female_count = next((r["n"] for r in by_sex if r["sex"] == "FEMALE"), 0)
    sex_total = male_count + female_count
    male_pct = round(male_count / sex_total * 100) if sex_total else 0
    female_pct = 100 - male_pct if sex_total else 0

    # 5. Regular vs Irregular Students
    by_enrollment_type = query_all(
        """
        SELECT enrollment_type, COUNT(*) AS n
        FROM students
        WHERE status = 'ACTIVE'
        GROUP BY enrollment_type
        """
    )
    regular_count = next((r["n"] for r in by_enrollment_type if r["enrollment_type"] == "REGULAR"), 0)
    irregular_count = next((r["n"] for r in by_enrollment_type if r["enrollment_type"] == "IRREGULAR"), 0)
    standing_total = regular_count + irregular_count
    irregular_pct = round(irregular_count / standing_total * 100) if standing_total else 0
    regular_pct = 100 - irregular_pct if standing_total else 0

    irregular_by_program = query_all(
        """
        SELECT program, COUNT(*) AS n
        FROM students
        WHERE status = 'ACTIVE' AND enrollment_type = 'IRREGULAR'
        GROUP BY program
        ORDER BY n DESC
        """
    )

    # 6. Class Average per Subject
    class_averages = _subject_class_averages(term_id)

    max_program = max([p["n"] for p in by_program], default=1) or 1
    max_year = max([y["n"] for y in by_year_level], default=1) or 1
    max_subject_sex = max(
        [max(r["male_count"] or 0, r["female_count"] or 0) for r in by_subject_sex], default=1
    ) or 1
    max_class_avg = max([c["avg"] for c in class_averages], default=1) or 1

    return render_template(
        "admin/analytics.html",
        term=term,
        by_program=by_program,
        max_program=max_program,
        by_year_level=by_year_level,
        max_year=max_year,
        by_subject_sex=by_subject_sex,
        max_subject_sex=max_subject_sex,
        male_count=male_count,
        female_count=female_count,
        male_pct=male_pct,
        female_pct=female_pct,
        sex_total=sex_total,
        regular_count=regular_count,
        irregular_count=irregular_count,
        regular_pct=regular_pct,
        irregular_pct=irregular_pct,
        irregular_by_program=irregular_by_program,
        class_averages=class_averages,
        max_class_avg=max_class_avg,
    )
