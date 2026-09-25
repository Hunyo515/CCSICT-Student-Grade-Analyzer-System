from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..auth import login_required
from ..db import execute, query_all, query_one
from ..notifications import notify
from ..grading import component_type, compute_weighted_total, gpa_scale, letter_grade, letter_grade_class
from .admin import active_term

student_bp = Blueprint("student", __name__, url_prefix="/student")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def current_student_id():
    student_id = session.get("student_id")
    if not student_id:
        abort(403)
    return student_id


def get_student(student_id=None):
    student_id = student_id or current_student_id()
    return query_one(
        """
        SELECT s.student_id, s.id_number, s.program, s.year_level, s.section,
               s.contact_number, s.status, u.full_name, u.email
        FROM students s JOIN users u ON u.user_id = s.user_id
        WHERE s.student_id = :id
        """,
        {"id": student_id},
    )


def my_enrollments(student_id, term_id):
    return query_all(
        """
        SELECT e.enrollment_id, e.assignment_id, ts.section, ts.status,
               s.subject_id, s.subject_code, s.subject_name, s.units,
               u.full_name AS teacher_name,
               (SELECT COUNT(*) FROM grade_components gc WHERE gc.assignment_id = ts.assignment_id) AS component_count
        FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
        JOIN subjects s ON s.subject_id = ts.subject_id
        JOIN teachers t ON t.teacher_id = ts.teacher_id
        JOIN users u ON u.user_id = t.user_id
        WHERE e.student_id = :sid AND ts.term_id = :term_id
        ORDER BY s.subject_name
        """,
        {"sid": student_id, "term_id": term_id},
    )


def assignment_components(assignment_id):
    return query_all(
        """
        SELECT component_id, component_name, weight_percent, category_id
        FROM grade_components
        WHERE assignment_id = :id
        ORDER BY component_id
        """,
        {"id": assignment_id},
    )


def scores_for_enrollment(enrollment_id):
    rows = query_all(
        "SELECT component_id, score, max_score FROM grades WHERE enrollment_id = :id",
        {"id": enrollment_id},
    )
    return {r["component_id"]: (r["score"], r["max_score"]) for r in rows}


def category_weights_for(assignment_id):
    """dict {category_id: weight_percent} for compute_weighted_total()."""
    rows = query_all(
        "SELECT category_id, weight_percent FROM grade_categories WHERE assignment_id = :id",
        {"id": assignment_id},
    )
    return {r["category_id"]: r["weight_percent"] for r in rows}


def overall_average(student_id, term_id):
    """
    Credit-weighted mean of weighted totals across this student's PUBLISHED
    subjects — each subject's percentage is weighted by its `units` (like a
    GPA), not just averaged flat. A 3-unit subject counts more than a
    1-unit subject toward the overall figure.
    """
    enrollments = [e for e in my_enrollments(student_id, term_id) if e["status"] == "PUBLISHED"]
    if not enrollments:
        return None

    weighted_sum = 0.0
    total_units = 0.0
    for e in enrollments:
        components = assignment_components(e["assignment_id"])
        scores = scores_for_enrollment(e["enrollment_id"])
        pct = compute_weighted_total(scores, components, category_weights_for(e["assignment_id"]))
        units = float(e["units"] or 1)
        weighted_sum += pct * units
        total_units += units

    return round(weighted_sum / total_units, 1) if total_units else None


def class_leaderboard(section, term_id):
    """Rank every student in the same section by their overall average."""
    classmates = query_all(
        """
        SELECT s.student_id, s.id_number, u.full_name
        FROM students s JOIN users u ON u.user_id = s.user_id
        WHERE s.section = :section AND s.status = 'ACTIVE'
        """,
        {"section": section},
    )

    ranked = []
    for c in classmates:
        avg = overall_average(c["student_id"], term_id)
        if avg is None:
            continue
        ranked.append({**c, "average": avg})

    ranked.sort(key=lambda r: r["average"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return ranked


def recent_assessments(student_id, limit=5):
    limit = int(limit)
    return query_all(
        f"""
        SELECT s.subject_name, gc.component_name, g.score, g.max_score, g.updated_at
        FROM grades g
        JOIN grade_components gc ON gc.component_id = g.component_id
        JOIN enrollments e ON e.enrollment_id = g.enrollment_id
        JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
        JOIN subjects s ON s.subject_id = ts.subject_id
        WHERE e.student_id = :sid AND g.score IS NOT NULL
        ORDER BY g.updated_at DESC
        FETCH FIRST {limit} ROWS ONLY
        """,
        {"sid": student_id},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@student_bp.route("/dashboard")
@login_required("student")
def dashboard():
    term = active_term()
    student = get_student()
    term_id = term["term_id"] if term else 0

    enrollments = my_enrollments(student["student_id"], term_id)
    avg = overall_average(student["student_id"], term_id)
    leaderboard = class_leaderboard(student["section"], term_id)
    my_rank_entry = next((r for r in leaderboard if r["student_id"] == student["student_id"]), None)

    stats = {
        "overall_average": avg,
        "subjects_enrolled": len(enrollments),
        "rank": my_rank_entry["rank"] if my_rank_entry else None,
        "class_size": len(leaderboard),
    }

    return render_template(
        "student/dashboard.html",
        term=term,
        student=student,
        enrollments=enrollments,
        stats=stats,
        recent=recent_assessments(student["student_id"]),
        join_error=request.args.get("join_error"),
        submitted_code=request.args.get("code"),
    )


@student_bp.route("/join-course", methods=["POST"])
@login_required("student")
def join_course():
    student = get_student()
    code = request.form.get("code", "").strip().upper()

    if not code:
        return redirect(url_for("student.dashboard", join_error="Please enter a class code."))

    assignment = query_one(
        """
        SELECT ts.assignment_id, ts.term_id, ts.enrollment_open, ts.section,
               s.subject_name, u.user_id AS teacher_user_id
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        JOIN teachers t ON t.teacher_id = ts.teacher_id
        JOIN users u ON u.user_id = t.user_id
        WHERE ts.join_code = :c
        """,
        {"c": code},
    )
    if not assignment:
        return redirect(url_for(
            "student.dashboard", join_error="Invalid or expired class code. Please check and try again.", code=code,
        ))
    if assignment["enrollment_open"] != "Y":
        return redirect(url_for(
            "student.dashboard", join_error="This class is not currently accepting self-enrollment.", code=code,
        ))

    existing = query_one(
        "SELECT enrollment_id FROM enrollments WHERE student_id = :sid AND assignment_id = :aid",
        {"sid": student["student_id"], "aid": assignment["assignment_id"]},
    )
    if existing:
        return redirect(url_for(
            "student.dashboard", join_error="You're already enrolled in this class.", code=code,
        ))

    execute(
        "INSERT INTO enrollments (student_id, assignment_id) VALUES (:sid, :aid)",
        {"sid": student["student_id"], "aid": assignment["assignment_id"]},
    )
    notify(
        assignment["teacher_user_id"],
        f"{student['full_name']} joined {assignment['subject_name']} ({assignment['section']}) via class code.",
        link=url_for("faculty.section_detail", assignment_id=assignment["assignment_id"]),
    )
    flash("You've successfully joined the class!", "success")
    return redirect(url_for("student.dashboard"))


# ---------------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------------

@student_bp.route("/grades")
@login_required("student")
def grades():
    term = active_term()
    student = get_student()
    term_id = term["term_id"] if term else 0
    enrollments = my_enrollments(student["student_id"], term_id)

    aid = request.args.get("assignment_id", type=int)
    selected = None
    if aid:
        selected = next((e for e in enrollments if e["assignment_id"] == aid), None)
    if not selected and enrollments:
        selected = enrollments[0]

    rows = []
    weighted_total = None
    letter = None
    letter_class = None
    passed = None

    if selected:
        components = assignment_components(selected["assignment_id"])
        scores = scores_for_enrollment(selected["enrollment_id"])
        for c in components:
            score, max_score = scores.get(c["component_id"], (None, None))
            rows.append({
                "name": c["component_name"],
                "type": component_type(c["component_name"]),
                "score": score,
                "max_score": max_score or 100,
                "weight": c["weight_percent"],
                "missed": score is None,
            })
        weighted_total = compute_weighted_total(scores, components, category_weights_for(selected["assignment_id"]))
        letter = letter_grade(weighted_total)
        letter_class = letter_grade_class(letter)
        passed = weighted_total >= 60

    return render_template(
        "student/grades.html",
        term=term,
        enrollments=enrollments,
        selected=selected,
        rows=rows,
        weighted_total=weighted_total,
        letter=letter,
        letter_class=letter_class,
        passed=passed,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@student_bp.route("/profile")
@login_required("student")
def profile():
    term = active_term()
    student = get_student()
    enrollments = my_enrollments(student["student_id"], term["term_id"] if term else 0)
    return render_template("student/profile.html", term=term, student=student, enrollments=enrollments)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@student_bp.route("/analytics")
@login_required("student")
def analytics():
    term = active_term()
    student = get_student()
    term_id = term["term_id"] if term else 0
    enrollments = my_enrollments(student["student_id"], term_id)

    subject_performance = []
    completed_count = 0
    missed_count = 0

    for e in enrollments:
        components = assignment_components(e["assignment_id"])
        scores = scores_for_enrollment(e["enrollment_id"])
        total = compute_weighted_total(scores, components, category_weights_for(e["assignment_id"]))
        subject_performance.append({
            "subject_name": e["subject_name"], "assignment_id": e["assignment_id"], "avg": total,
        })
        for c in components:
            score, max_score = scores.get(c["component_id"], (None, None))
            if score is not None and max_score:
                completed_count += 1
            else:
                missed_count += 1

    max_subject = max([s["avg"] for s in subject_performance], default=1) or 1

    # Per-component breakdown for one selected subject (defaults to the first enrollment)
    aid = request.args.get("assignment_id", type=int)
    selected = next((e for e in enrollments if e["assignment_id"] == aid), None) or (enrollments[0] if enrollments else None)
    component_breakdown = []
    if selected:
        components = assignment_components(selected["assignment_id"])
        scores = scores_for_enrollment(selected["enrollment_id"])
        for c in components:
            score, max_score = scores.get(c["component_id"], (None, None))
            if score is not None and max_score:
                component_breakdown.append({
                    "name": c["component_name"], "pct": round((float(score) / float(max_score)) * 100, 1),
                })

    # Grade trend across all terms the student has published grades in
    all_terms = query_all("SELECT term_id, school_year, semester FROM school_terms ORDER BY term_id")
    term_trend = []
    for t in all_terms:
        avg = overall_average(student["student_id"], t["term_id"])
        if avg is not None:
            term_trend.append({"label": f"{t['semester']} {t['school_year']}", "avg": avg})
    max_trend = max([t["avg"] for t in term_trend], default=1) or 1

    gpa = gpa_scale(subject_performance and (sum(s["avg"] for s in subject_performance) / len(subject_performance)))
    gpa_trend = None
    if len(term_trend) >= 2:
        gpa_trend = round(gpa_scale(term_trend[-1]["avg"]) - gpa_scale(term_trend[-2]["avg"]), 2)

    total_activities = completed_count + missed_count
    completion_pct = round((completed_count / total_activities) * 100) if total_activities else 0

    return render_template(
        "student/analytics.html",
        term=term,
        enrollments=enrollments,
        subject_performance=subject_performance,
        max_subject=max_subject,
        selected=selected,
        component_breakdown=component_breakdown,
        term_trend=term_trend,
        max_trend=max_trend,
        gpa=gpa,
        gpa_trend=gpa_trend,
        completed_count=completed_count,
        missed_count=missed_count,
        total_activities=total_activities,
        completion_pct=completion_pct,
    )


# ---------------------------------------------------------------------------
# My Rank
# ---------------------------------------------------------------------------

@student_bp.route("/my-rank")
@login_required("student")
def my_rank():
    term = active_term()
    student = get_student()
    term_id = term["term_id"] if term else 0

    leaderboard = class_leaderboard(student["section"], term_id)
    my_entry = next((r for r in leaderboard if r["student_id"] == student["student_id"]), None)

    return render_template(
        "student/my_rank.html",
        term=term,
        student=student,
        leaderboard=leaderboard,
        my_entry=my_entry,
        class_size=len(leaderboard),
    )
