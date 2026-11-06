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
<<<<<<< HEAD
    row=query_one(
        """
        SELECT s.student_id, s.id_number, s.program, s.year_level, s.section,
               s.contact_number, s.status, s.age, s.enrollment_type, u.full_name, u.email
=======
    return query_one(
        """
        SELECT s.student_id, s.id_number, s.program, s.year_level, s.section,
               s.contact_number, s.status, u.full_name, u.email
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        FROM students s JOIN users u ON u.user_id = s.user_id
        WHERE s.student_id = :id
        """,
        {"id": student_id},
    )
<<<<<<< HEAD
    if row:
        from ..student_progress import residency
        from .. import academic
        row.update(residency(row,academic.active()))
    return row

=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


def my_enrollments(student_id, term_id):
    return query_all(
        """
<<<<<<< HEAD
        SELECT e.enrollment_id, e.assignment_id, ts.section, ts.status, ac.school_year, ac.semester,
               s.subject_id, s.subject_code, s.subject_name, s.units,
               COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name,
               (SELECT COUNT(*) FROM grade_components gc WHERE gc.assignment_id = ts.assignment_id) AS component_count
        FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
        JOIN school_terms ac ON ac.term_id=ts.term_id
        JOIN subjects s ON s.subject_id = ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id = ts.teacher_id
        LEFT JOIN users u ON u.user_id = t.user_id
        WHERE e.student_id = :sid AND (:term_id IS NULL OR ts.term_id = :term_id)
=======
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
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
<<<<<<< HEAD
    """Bulk-load published class grades; avoid one query per student/subject."""
    rows = query_all(
        """
        SELECT s.student_id, u.full_name, e.enrollment_id, subj.units,
               gc.component_id, gc.weight_percent, gc.category_id,
               cat.weight_percent AS category_weight, g.score, g.max_score
        FROM students s JOIN users u ON u.user_id=s.user_id
        JOIN enrollments e ON e.student_id=s.student_id
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        JOIN subjects subj ON subj.subject_id=ts.subject_id
        LEFT JOIN grade_components gc ON gc.assignment_id=ts.assignment_id
        LEFT JOIN grade_categories cat ON cat.category_id=gc.category_id
        LEFT JOIN grades g ON g.enrollment_id=e.enrollment_id AND g.component_id=gc.component_id
        WHERE s.section=:section AND s.status='ACTIVE' AND u.status='ACTIVE'
          AND ts.term_id=:term_id AND ts.status='PUBLISHED'
        """, {"section": section, "term_id": term_id})
    groups = {}
    for row in rows:
        key = (row["student_id"], row["enrollment_id"])
        entry = groups.setdefault(key, {"name": row["full_name"], "units": float(row["units"]), "components": [], "scores": {}, "categories": {}})
        if row["component_id"] is not None:
            entry["components"].append(row)
            entry["scores"][row["component_id"]] = (row["score"], row["max_score"])
            if row["category_id"] is not None:
                entry["categories"][row["category_id"]] = row["category_weight"]
    totals = {}
    for (sid, _), entry in groups.items():
        item = totals.setdefault(sid, {"student_id": sid, "full_name": entry["name"], "sum": 0.0, "units": 0.0})
        item["sum"] += compute_weighted_total(entry["scores"], entry["components"], entry["categories"]) * entry["units"]
        item["units"] += entry["units"]
    ranked = [{"student_id": v["student_id"], "full_name": v["full_name"], "average": round(v["sum"] / v["units"], 1)} for v in totals.values() if v["units"] > 0]
    ranked.sort(key=lambda row: (-row["average"], row["student_id"]))
    previous = None
    rank = 0
    for position, row in enumerate(ranked, 1):
        if row["average"] != previous:
            rank = position
        row["rank"] = rank
        previous = row["average"]
=======
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
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
<<<<<<< HEAD
        WHERE e.student_id = :sid AND ts.status = 'PUBLISHED' AND g.score IS NOT NULL AND g.max_score > 0
=======
        WHERE e.student_id = :sid AND g.score IS NOT NULL
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
<<<<<<< HEAD
    from ..insights import load_sections, student_summary, term_history
    term = active_term()
    student = get_student()
    term_id = term["term_id"] if term else 0
    history = load_sections(student_id=student["student_id"])
    sections = [s for s in history if s['term_id'] == term_id]
    return render_template("student/dashboard.html", term=term, student=student,
        sections=sections, report=student_summary(sections), trend=term_history(history),
        enrollments=my_enrollments(student["student_id"], term_id),
        join_error=request.args.get("join_error"), submitted_code=request.args.get("code"))
=======
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
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


@student_bp.route("/join-course", methods=["POST"])
@login_required("student")
def join_course():
    student = get_student()
<<<<<<< HEAD
    from ..security import rate_limit
    rate_limit("join:" + str(student["student_id"]), 10, 900)
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    code = request.form.get("code", "").strip().upper()

    if not code:
        return redirect(url_for("student.dashboard", join_error="Please enter a class code."))

    assignment = query_one(
        """
        SELECT ts.assignment_id, ts.term_id, ts.enrollment_open, ts.section,
<<<<<<< HEAD
               ts.subject_id, ts.status, s.program, s.year_level,
               s.subject_name, u.user_id AS teacher_user_id
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id = ts.teacher_id
        LEFT JOIN users u ON u.user_id = t.user_id
=======
               s.subject_name, u.user_id AS teacher_user_id
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        JOIN teachers t ON t.teacher_id = ts.teacher_id
        JOIN users u ON u.user_id = t.user_id
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        WHERE ts.join_code = :c
        """,
        {"c": code},
    )
    if not assignment:
        return redirect(url_for(
            "student.dashboard", join_error="Invalid or expired class code. Please check and try again.", code=code,
        ))
<<<<<<< HEAD
    term = active_term()
    if not term or assignment["term_id"] != term["term_id"] or assignment["enrollment_open"] != "Y":
=======
    if assignment["enrollment_open"] != "Y":
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        return redirect(url_for(
            "student.dashboard", join_error="This class is not currently accepting self-enrollment.", code=code,
        ))

<<<<<<< HEAD
    locked=query_one('SELECT status,enrollment_open FROM teacher_subjects WHERE assignment_id=:id FOR UPDATE WAIT 5',{'id':assignment['assignment_id']})
    if not locked or locked['status']=='PUBLISHED' or locked['enrollment_open']!='Y':
        return redirect(url_for('student.dashboard',join_error='This class is not accepting enrollment. Contact your administrator.',code=code))
    from ..curriculum import cohort_matches
    current=query_one('SELECT student_id,program,year_level,section,status FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':student['student_id']})
    if not current or current['status']!='ACTIVE' or not cohort_matches(current,assignment,assignment['section']):
        return redirect(url_for('student.dashboard',join_error='Ask your administrator to enroll you as an individual exception for this class.',code=code))

    existing = query_one(
        """SELECT e.enrollment_id FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        WHERE e.student_id=:sid AND ts.subject_id=:subject AND ts.term_id=:term FETCH FIRST 1 ROWS ONLY""",
        {"sid": student["student_id"], "subject": assignment['subject_id'], 'term': assignment['term_id']},
    )
    if existing:
        return redirect(url_for(
            "student.dashboard", join_error="You're already enrolled in this subject for this term.", code=code,
=======
    existing = query_one(
        "SELECT enrollment_id FROM enrollments WHERE student_id = :sid AND assignment_id = :aid",
        {"sid": student["student_id"], "aid": assignment["assignment_id"]},
    )
    if existing:
        return redirect(url_for(
            "student.dashboard", join_error="You're already enrolled in this class.", code=code,
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        ))

    execute(
        "INSERT INTO enrollments (student_id, assignment_id) VALUES (:sid, :aid)",
        {"sid": student["student_id"], "aid": assignment["assignment_id"]},
    )
<<<<<<< HEAD
    execute('UPDATE teacher_subjects SET revision=revision+1 WHERE assignment_id=:id',{'id':assignment['assignment_id']})
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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

<<<<<<< HEAD
    if selected and selected["status"] == "PUBLISHED":
=======
    if selected:
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
<<<<<<< HEAD
        passed = weighted_total >= 75
=======
        passed = weighted_total >= 60
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423

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

<<<<<<< HEAD
@student_bp.route("/profile",methods=['GET','POST'])
=======
@student_bp.route("/profile")
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
@login_required("student")
def profile():
    term = active_term()
    student = get_student()
<<<<<<< HEAD
    if request.method=='POST':abort(403,description='Personal information is read-only. Contact your administrator for corrections.')
    from .. import academic
    from ..student_progress import academic_status,curriculum,passed_subjects
    term=academic.active()
    student["enrollment_type"]=academic_status(dict(student,year_level=student.get("curriculum_year",student["year_level"])),term,curriculum(student["program"]),passed_subjects(student["student_id"]))
    return render_template("student/profile.html", term=term, student=student)


@student_bp.route('/profile/photo',methods=['GET','POST'])
@login_required('student')
def profile_photo():
    from flask import send_file
    from ..profile_photos import photo_path,prepare_photo
    path=photo_path(session['user_id'])
    if request.method=='GET':
        if not path.is_file():abort(404)
        response=send_file(path,mimetype='image/jpeg',max_age=0);response.headers['Cache-Control']='private, no-cache';return response
    uploaded=request.files.get('profile_photo')
    if not uploaded:abort(400,description='Choose a profile picture.')
    try:data=prepare_photo(uploaded.stream)
    except ValueError as error:abort(400,description=str(error))
    import os,tempfile
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.jpg',delete=False) as temp:
        temp.write(data);temporary=temp.name
    try:os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    flash('Profile picture updated.','success');return redirect(url_for('student.profile'))
=======
    enrollments = my_enrollments(student["student_id"], term["term_id"] if term else 0)
    return render_template("student/profile.html", term=term, student=student, enrollments=enrollments)
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@student_bp.route("/analytics")
@login_required("student")
def analytics():
<<<<<<< HEAD
    from ..insights import load_sections, student_summary, term_history
    term = active_term()
    student = get_student()
    all_sections = load_sections(student_id=student["student_id"])
    sections = [s for s in all_sections if term and s["term_id"] == term["term_id"]]
    published = [s for s in sections if s["status"] == "PUBLISHED"]
    aid = request.args.get("assignment_id", type=int)
    selected = next((s for s in published if s["assignment_id"] == aid), None) or (published[0] if published else None)
    trend = term_history(all_sections)
    return render_template("student/analytics.html", term=term, sections=sections,
        published=published, selected=selected, trend=trend, report=student_summary(sections))
=======
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
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


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
<<<<<<< HEAD
        leaderboard=[my_entry] if my_entry else [],
=======
        leaderboard=leaderboard,
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        my_entry=my_entry,
        class_size=len(leaderboard),
    )
