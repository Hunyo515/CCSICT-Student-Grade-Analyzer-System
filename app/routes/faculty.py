import csv
import io
import random
import string

from flask import (
    Blueprint, Response, abort, flash, redirect, render_template,
    request, session, url_for,
)

from ..auth import login_required
from ..db import execute, query_all, query_one
from ..notifications import notify, notify_many
from ..grading import compute_weighted_total, letter_grade, letter_grade_class
from .admin import active_term, log_activity  # reuse shared helpers

faculty_bp = Blueprint("faculty", __name__, url_prefix="/faculty")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def current_teacher_id():
    teacher_id = session.get("teacher_id")
    if not teacher_id:
        abort(403)
    return teacher_id


def my_assignments(term_id):
    """All (subject, section) assignments for the logged-in teacher this term."""
    return query_all(
        """
        SELECT ts.assignment_id, ts.section, ts.status, s.subject_id, s.subject_code, s.subject_name
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        WHERE ts.teacher_id = :tid AND ts.term_id = :term_id
        ORDER BY s.subject_name, ts.section
        """,
        {"tid": current_teacher_id(), "term_id": term_id},
    )


def get_assignment_or_404(assignment_id):
    row = query_one(
        """
        SELECT ts.assignment_id, ts.section, ts.status, ts.teacher_id,
               s.subject_id, s.subject_code, s.subject_name
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        WHERE ts.assignment_id = :id
        """,
        {"id": assignment_id},
    )
    if not row or row["teacher_id"] != current_teacher_id():
        abort(404)
    return row


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


def assignment_categories(assignment_id):
    """All grade-weighting categories a teacher has defined for this
    assignment, e.g. [{'category_id': 1, 'category_name': 'Lecture', 'weight_percent': 60}, ...].
    Empty list means the assignment is in "flat" mode (no categories at all)."""
    return query_all(
        """
        SELECT category_id, category_name, weight_percent, display_order
        FROM grade_categories
        WHERE assignment_id = :id
        ORDER BY display_order, category_id
        """,
        {"id": assignment_id},
    )


def category_weights_for(assignment_id):
    """dict {category_id: weight_percent} for compute_weighted_total()."""
    return {c["category_id"]: c["weight_percent"] for c in assignment_categories(assignment_id)}


def assignment_enrollments(assignment_id, q=""):
    where = "WHERE e.assignment_id = :id"
    params = {"id": assignment_id}
    if q:
        where += " AND (LOWER(u.full_name) LIKE :q OR LOWER(s.id_number) LIKE :q)"
        params["q"] = f"%{q.lower()}%"

    return query_all(
        f"""
        SELECT e.enrollment_id, s.student_id, s.id_number, u.full_name
        FROM enrollments e
        JOIN students s ON s.student_id = e.student_id
        JOIN users u ON u.user_id = s.user_id
        {where}
        ORDER BY u.full_name
        """,
        params,
    )


def scores_by_enrollment(assignment_id):
    """dict[enrollment_id] -> dict[component_id] -> (score, max_score)"""
    rows = query_all(
        """
        SELECT e.enrollment_id, g.component_id, g.score, g.max_score
        FROM enrollments e
        JOIN grades g ON g.enrollment_id = e.enrollment_id
        WHERE e.assignment_id = :id
        """,
        {"id": assignment_id},
    )
    result = {}
    for r in rows:
        result.setdefault(r["enrollment_id"], {})[r["component_id"]] = (r["score"], r["max_score"])
    return result


def selected_assignment_id(assignments):
    aid = request.args.get("assignment_id", type=int)
    if aid and any(a["assignment_id"] == aid for a in assignments):
        return aid
    return assignments[0]["assignment_id"] if assignments else None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@faculty_bp.route("/dashboard")
@login_required("faculty")
def dashboard():
    term = active_term()
    teacher_id = current_teacher_id()

    assignments = query_all(
        """
        SELECT ts.assignment_id, ts.section, ts.status, s.subject_code, s.subject_name,
               (SELECT COUNT(*) FROM enrollments e WHERE e.assignment_id = ts.assignment_id) AS student_count
        FROM teacher_subjects ts
        JOIN subjects s ON s.subject_id = ts.subject_id
        WHERE ts.teacher_id = :tid AND ts.term_id = :term_id
        ORDER BY s.subject_name, ts.section
        """,
        {"tid": teacher_id, "term_id": term["term_id"] if term else 0},
    )

    stats = {
        "assigned_subjects": query_one(
            "SELECT COUNT(DISTINCT subject_id) AS n FROM teacher_subjects WHERE teacher_id = :tid AND term_id = :term_id",
            {"tid": teacher_id, "term_id": term["term_id"] if term else 0},
        )["n"],
        "total_students": query_one(
            """
            SELECT COUNT(*) AS n FROM enrollments e
            JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
            WHERE ts.teacher_id = :tid AND ts.term_id = :term_id
            """,
            {"tid": teacher_id, "term_id": term["term_id"] if term else 0},
        )["n"],
        "pending_entries": query_one(
            """
            SELECT COUNT(*) AS n FROM enrollments e
            JOIN teacher_subjects ts ON ts.assignment_id = e.assignment_id
            WHERE ts.teacher_id = :tid AND ts.term_id = :term_id AND ts.status != 'PUBLISHED'
            """,
            {"tid": teacher_id, "term_id": term["term_id"] if term else 0},
        )["n"],
    }

    return render_template("faculty/dashboard.html", term=term, assignments=assignments, stats=stats)


# ---------------------------------------------------------------------------
# Grade Entry
# ---------------------------------------------------------------------------

@faculty_bp.route("/grade-entry")
@login_required("faculty")
def grade_entry():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/grade_entry.html", term=term, assignments=[], assignment=None,
            components=[], students=[], scores={}, q="", allocation_total=0,
        )

    assignment = get_assignment_or_404(aid)
    components = assignment_components(aid)
    q = request.args.get("q", "").strip()
    students = assignment_enrollments(aid, q)
    scores = scores_by_enrollment(aid)
    allocation_total = sum(c["weight_percent"] for c in components if not c.get("category_id"))
    has_categories = len(assignment_categories(aid)) > 0

    return render_template(
        "faculty/grade_entry.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        components=components,
        students=students,
        scores=scores,
        q=q,
        allocation_total=allocation_total,
        has_categories=has_categories,
    )


@faculty_bp.route("/grade-entry/component/add", methods=["POST"])
@login_required("faculty")
def add_component():
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)

    name = request.form.get("component_name", "").strip()
    weight = request.form.get("weight_percent", "0").strip()
    category_id = request.form.get("category_id", type=int)  # None/blank = flat (uncategorized)
    redirect_to = request.form.get("redirect_to", "grade_entry")

    if not name:
        flash("Component name is required.", "error")
        return redirect(url_for(f"faculty.{redirect_to}", assignment_id=assignment_id))

    execute(
        "INSERT INTO grade_components (assignment_id, component_name, weight_percent, category_id) "
        "VALUES (:aid, :name, :weight, :category_id)",
        {"aid": assignment_id, "name": name, "weight": weight, "category_id": category_id},
    )
    flash(f"Component '{name}' added.", "success")
    return redirect(url_for(f"faculty.{redirect_to}", assignment_id=assignment_id))


@faculty_bp.route("/grade-entry/component/<int:component_id>/delete", methods=["POST"])
@login_required("faculty")
def delete_component(component_id):
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)
    redirect_to = request.form.get("redirect_to", "grade_entry")
    execute("DELETE FROM grade_components WHERE component_id = :id AND assignment_id = :aid",
            {"id": component_id, "aid": assignment_id})
    flash("Component removed.", "success")
    return redirect(url_for(f"faculty.{redirect_to}", assignment_id=assignment_id))


# ---------------------------------------------------------------------------
# Grade Weighting Configuration (Lecture / Laboratory split)
# ---------------------------------------------------------------------------

@faculty_bp.route("/grade-weighting")
@login_required("faculty")
def grade_weighting():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/grade_weighting.html", term=term, assignments=[], assignment=None,
        )

    assignment = get_assignment_or_404(aid)
    categories = assignment_categories(aid)
    components = assignment_components(aid)
    uncategorized = [c for c in components if not c.get("category_id")]

    for cat in categories:
        cat["components"] = [c for c in components if c.get("category_id") == cat["category_id"]]
        cat["allocation_total"] = sum(c["weight_percent"] for c in cat["components"])
        for c in cat["components"]:
            c["final_contribution"] = round(float(c["weight_percent"]) * float(cat["weight_percent"]) / 100.0, 1)

    categories_total = sum(cat["weight_percent"] for cat in categories)
    split_valid = not categories or categories_total == 100
    flat_total = sum(c["weight_percent"] for c in uncategorized)

    return render_template(
        "faculty/grade_weighting.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        categories=categories,
        uncategorized=uncategorized,
        flat_total=flat_total,
        categories_total=categories_total,
        split_valid=split_valid,
    )


@faculty_bp.route("/grade-weighting/category/add", methods=["POST"])
@login_required("faculty")
def add_category():
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)

    name = request.form.get("category_name", "").strip()
    weight = request.form.get("weight_percent", "").strip()

    if not name:
        flash("Category name is required.", "error")
        return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))
    try:
        weight_val = float(weight)
    except ValueError:
        flash("Category weight must be a number.", "error")
        return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))

    next_order = query_one(
        "SELECT COALESCE(MAX(display_order), 0) + 1 AS n FROM grade_categories WHERE assignment_id = :id",
        {"id": assignment_id},
    )["n"]

    execute(
        "INSERT INTO grade_categories (assignment_id, category_name, weight_percent, display_order) "
        "VALUES (:aid, :name, :weight, :display_order)",
        {"aid": assignment_id, "name": name, "weight": weight_val, "display_order": next_order},
    )
    flash(f"Category '{name}' added.", "success")
    return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))


@faculty_bp.route("/grade-weighting/category/<int:category_id>/edit", methods=["POST"])
@login_required("faculty")
def edit_category(category_id):
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)

    name = request.form.get("category_name", "").strip()
    weight = request.form.get("weight_percent", "").strip()

    if not name:
        flash("Category name is required.", "error")
        return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))
    try:
        weight_val = float(weight)
    except ValueError:
        flash("Category weight must be a number.", "error")
        return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))

    execute(
        "UPDATE grade_categories SET category_name = :name, weight_percent = :weight "
        "WHERE category_id = :id AND assignment_id = :aid",
        {"name": name, "weight": weight_val, "id": category_id, "aid": assignment_id},
    )
    flash("Category updated.", "success")
    return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))


@faculty_bp.route("/grade-weighting/category/<int:category_id>/delete", methods=["POST"])
@login_required("faculty")
def delete_category(category_id):
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)
    # Cascades: any components inside this category are removed with it
    # (grade_components.category_id has ON DELETE CASCADE).
    execute(
        "DELETE FROM grade_categories WHERE category_id = :id AND assignment_id = :aid",
        {"id": category_id, "aid": assignment_id},
    )
    flash("Category removed (and any components inside it).", "success")
    return redirect(url_for("faculty.grade_weighting", assignment_id=assignment_id))


@faculty_bp.route("/grade-entry/scores/save", methods=["POST"])
@login_required("faculty")
def save_scores():
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)

    saved = 0
    for key, value in request.form.items():
        if not key.startswith("score__") or value.strip() == "":
            continue
        _, enrollment_id, component_id = key.split("__")
        try:
            score = float(value)
        except ValueError:
            continue

        execute(
            """
            MERGE INTO grades g
            USING (SELECT :eid AS enrollment_id, :cid AS component_id FROM dual) src
            ON (g.enrollment_id = src.enrollment_id AND g.component_id = src.component_id)
            WHEN MATCHED THEN UPDATE SET score = :score, updated_at = SYSTIMESTAMP
            WHEN NOT MATCHED THEN INSERT (enrollment_id, component_id, score, max_score)
                VALUES (:eid, :cid, :score, 100)
            """,
            {"eid": enrollment_id, "cid": component_id, "score": score},
        )
        saved += 1

    # Move status from DRAFT to IN_PROGRESS on first save
    execute(
        "UPDATE teacher_subjects SET status = 'IN_PROGRESS' WHERE assignment_id = :id AND status = 'DRAFT'",
        {"id": assignment_id},
    )

    flash(f"Saved {saved} score entr{'y' if saved == 1 else 'ies'}.", "success")
    return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))


@faculty_bp.route("/grade-entry/status", methods=["POST"])
@login_required("faculty")
def update_status():
    assignment_id = request.form.get("assignment_id", type=int)
    new_status = request.form.get("status")
    assignment = get_assignment_or_404(assignment_id)

    if new_status not in ("DRAFT", "IN_PROGRESS", "PUBLISHED"):
        abort(400)

    execute("UPDATE teacher_subjects SET status = :s WHERE assignment_id = :id", {"s": new_status, "id": assignment_id})

    if new_status == "PUBLISHED":
        log_activity(f"Teacher {session.get('full_name')} published {assignment['subject_name']} grades")
        students = query_all(
            "SELECT s.user_id FROM enrollments e JOIN students s ON s.student_id = e.student_id "
            "WHERE e.assignment_id = :id",
            {"id": assignment_id},
        )
        notify_many(
            [s["user_id"] for s in students],
            f"Your grades for {assignment['subject_name']} ({assignment['section']}) have been published.",
            link=url_for("student.grades", assignment_id=assignment_id),
        )
        flash("Grades published.", "success")
    else:
        flash("Draft saved.", "success")

    return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))


# ---------------------------------------------------------------------------
# CSV import (upload -> preview -> confirm)
# ---------------------------------------------------------------------------

@faculty_bp.route("/grade-entry/csv/upload", methods=["POST"])
@login_required("faculty")
def csv_upload():
    assignment_id = request.form.get("assignment_id", type=int)
    assignment = get_assignment_or_404(assignment_id)

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        flash("Please choose a CSV file to import.", "error")
        return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))

    try:
        content = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Could not read that file as UTF-8 CSV.", "error")
        return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))

    reader = csv.DictReader(io.StringIO(content))
    required_cols = {"id_number", "component_name", "score"}
    if not required_cols.issubset({(c or "").strip().lower() for c in (reader.fieldnames or [])}):
        flash("CSV must have columns: id_number, component_name, score", "error")
        return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))

    students = {s["id_number"]: s for s in assignment_enrollments(assignment_id)}
    components = {c["component_name"].lower(): c for c in assignment_components(assignment_id)}

    valid_rows, invalid_rows = [], []
    for row in reader:
        id_number = (row.get("id_number") or "").strip()
        comp_name = (row.get("component_name") or "").strip()
        score_raw = (row.get("score") or "").strip()

        student = students.get(id_number)
        component = components.get(comp_name.lower())
        error = None
        if not student:
            error = "Unknown student ID"
        elif not component:
            error = "Unknown component"
        else:
            try:
                float(score_raw)
            except ValueError:
                error = "Score is not a number"

        record = {
            "id_number": id_number,
            "full_name": student["full_name"] if student else "",
            "component_name": comp_name,
            "score": score_raw,
            "enrollment_id": student["enrollment_id"] if student else None,
            "component_id": component["component_id"] if component else None,
        }
        if error:
            record["error"] = error
            invalid_rows.append(record)
        else:
            valid_rows.append(record)

    session["csv_preview"] = {
        "assignment_id": assignment_id,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
    }
    return redirect(url_for("faculty.csv_preview"))


@faculty_bp.route("/grade-entry/csv/preview")
@login_required("faculty")
def csv_preview():
    data = session.get("csv_preview")
    if not data:
        flash("No CSV import in progress.", "error")
        return redirect(url_for("faculty.grade_entry"))

    assignment = get_assignment_or_404(data["assignment_id"])
    return render_template(
        "faculty/csv_preview.html",
        assignment=assignment,
        valid_rows=data["valid_rows"],
        invalid_rows=data["invalid_rows"],
    )


@faculty_bp.route("/grade-entry/csv/confirm", methods=["POST"])
@login_required("faculty")
def csv_confirm():
    data = session.pop("csv_preview", None)
    if not data:
        flash("No CSV import in progress.", "error")
        return redirect(url_for("faculty.grade_entry"))

    assignment_id = data["assignment_id"]
    get_assignment_or_404(assignment_id)

    imported = 0
    for row in data["valid_rows"]:
        execute(
            """
            MERGE INTO grades g
            USING (SELECT :eid AS enrollment_id, :cid AS component_id FROM dual) src
            ON (g.enrollment_id = src.enrollment_id AND g.component_id = src.component_id)
            WHEN MATCHED THEN UPDATE SET score = :score, updated_at = SYSTIMESTAMP
            WHEN NOT MATCHED THEN INSERT (enrollment_id, component_id, score, max_score)
                VALUES (:eid, :cid, :score, 100)
            """,
            {"eid": row["enrollment_id"], "cid": row["component_id"], "score": float(row["score"])},
        )
        imported += 1

    execute(
        "UPDATE teacher_subjects SET status = 'IN_PROGRESS' WHERE assignment_id = :id AND status = 'DRAFT'",
        {"id": assignment_id},
    )
    flash(f"Imported {imported} score{'s' if imported != 1 else ''} from CSV.", "success")
    return redirect(url_for("faculty.grade_entry", assignment_id=assignment_id))


@faculty_bp.route("/grade-entry/csv/cancel", methods=["POST"])
@login_required("faculty")
def csv_cancel():
    data = session.pop("csv_preview", None)
    aid = data["assignment_id"] if data else None
    flash("CSV import cancelled.", "success")
    return redirect(url_for("faculty.grade_entry", assignment_id=aid))


# ---------------------------------------------------------------------------
# Shared computation for analytics / top performers / export
# ---------------------------------------------------------------------------

def compute_rankings(assignment_id):
    components = assignment_components(assignment_id)
    students = assignment_enrollments(assignment_id)
    scores = scores_by_enrollment(assignment_id)
    splits = category_weights_for(assignment_id)

    ranked = []
    for s in students:
        total = compute_weighted_total(scores.get(s["enrollment_id"], {}), components, splits)
        letter = letter_grade(total)
        ranked.append({**s, "weighted_total": total, "letter": letter, "letter_class": letter_grade_class(letter)})

    ranked.sort(key=lambda r: r["weighted_total"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return components, ranked


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@faculty_bp.route("/analytics")
@login_required("faculty")
def analytics():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/analytics.html", term=term, assignments=[], assignment=None,
            component_averages=[], grade_distribution=[], max_component=1, max_distribution=1,
        )

    assignment = get_assignment_or_404(aid)
    components, ranked = compute_rankings(aid)
    scores = scores_by_enrollment(aid)

    component_averages = []
    for c in components:
        vals = [
            (s / m * 100) for eid in scores for cid, (s, m) in scores[eid].items()
            if cid == c["component_id"] and s is not None and m
        ]
        avg = round(sum(vals) / len(vals), 1) if vals else 0
        component_averages.append({"name": c["component_name"], "avg": avg})

    buckets = ["Grade A", "Grade B+", "Grade B", "Grade C+", "Grade C", "Grade D", "Grade F"]
    grade_distribution = [{"letter": b, "count": sum(1 for r in ranked if r["letter"] == b)} for b in buckets]

    max_component = max([c["avg"] for c in component_averages], default=1) or 1
    max_distribution = max([g["count"] for g in grade_distribution], default=1) or 1

    return render_template(
        "faculty/analytics.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        component_averages=component_averages,
        grade_distribution=grade_distribution,
        max_component=max_component,
        max_distribution=max_distribution,
    )


# ---------------------------------------------------------------------------
# Top Performers
# ---------------------------------------------------------------------------

@faculty_bp.route("/top-performers")
@login_required("faculty")
def top_performers():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/top_performers.html", term=term, assignments=[], assignment=None, ranked=[],
        )

    assignment = get_assignment_or_404(aid)
    _, ranked = compute_rankings(aid)

    return render_template(
        "faculty/top_performers.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        ranked=ranked,
    )


# ---------------------------------------------------------------------------
# Section detail (enrollment code + roster preview)
# ---------------------------------------------------------------------------

def _generate_join_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(alphabet, k=6))
        if not query_one("SELECT 1 FROM teacher_subjects WHERE join_code = :c", {"c": code}):
            return code


@faculty_bp.route("/section-detail")
@login_required("faculty")
def section_detail():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/section_detail.html", term=term, assignments=[], assignment=None,
            roster=[], enrolled_count=0,
        )

    assignment = get_assignment_or_404(aid)
    row = query_one(
        "SELECT join_code, enrollment_open FROM teacher_subjects WHERE assignment_id = :id",
        {"id": aid},
    )
    if not row["join_code"]:
        code = _generate_join_code()
        execute(
            "UPDATE teacher_subjects SET join_code = :c WHERE assignment_id = :id",
            {"c": code, "id": aid},
        )
        join_code, enrollment_open = code, row["enrollment_open"]
    else:
        join_code, enrollment_open = row["join_code"], row["enrollment_open"]

    roster = query_all(
        """
        SELECT s.id_number, u.full_name, s.program, s.year_level, e.created_at
        FROM enrollments e
        JOIN students s ON s.student_id = e.student_id
        JOIN users u ON u.user_id = s.user_id
        WHERE e.assignment_id = :id
        ORDER BY e.created_at
        FETCH FIRST 5 ROWS ONLY
        """,
        {"id": aid},
    )
    enrolled_count = query_one(
        "SELECT COUNT(*) AS c FROM enrollments WHERE assignment_id = :id", {"id": aid}
    )["c"]

    return render_template(
        "faculty/section_detail.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        join_code=join_code,
        enrollment_open=(enrollment_open == "Y"),
        roster=roster,
        enrolled_count=enrolled_count,
    )


@faculty_bp.route("/section-detail/toggle", methods=["POST"])
@login_required("faculty")
def section_detail_toggle():
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)  # ownership check
    row = query_one(
        "SELECT enrollment_open FROM teacher_subjects WHERE assignment_id = :id", {"id": assignment_id}
    )
    new_value = "N" if row["enrollment_open"] == "Y" else "Y"
    execute(
        "UPDATE teacher_subjects SET enrollment_open = :v WHERE assignment_id = :id",
        {"v": new_value, "id": assignment_id},
    )
    flash("Enrollment link " + ("opened." if new_value == "Y" else "closed."), "success")
    return redirect(url_for("faculty.section_detail", assignment_id=assignment_id))


@faculty_bp.route("/section-detail/regenerate", methods=["POST"])
@login_required("faculty")
def section_detail_regenerate():
    assignment_id = request.form.get("assignment_id", type=int)
    get_assignment_or_404(assignment_id)  # ownership check
    code = _generate_join_code()
    execute(
        "UPDATE teacher_subjects SET join_code = :c WHERE assignment_id = :id",
        {"c": code, "id": assignment_id},
    )
    flash("New enrollment code generated.", "success")
    return redirect(url_for("faculty.section_detail", assignment_id=assignment_id))


# ---------------------------------------------------------------------------
# Grade export (CSV download)
# ---------------------------------------------------------------------------

PASS_THRESHOLD = 75  # weighted percentage cutoff used for the Pass/Fail remark


@faculty_bp.route("/grade-entry/registry")
@login_required("faculty")
def grade_registry():
    term = active_term()
    assignments = my_assignments(term["term_id"] if term else 0)
    aid = selected_assignment_id(assignments)

    if not aid:
        return render_template(
            "faculty/grade_registry.html", term=term, assignments=[], assignment=None,
            components=[], rows=[],
        )

    assignment = get_assignment_or_404(aid)
    components = assignment_components(aid)
    students = assignment_enrollments(aid)
    scores = scores_by_enrollment(aid)
    splits = category_weights_for(aid)

    rows = []
    for s in students:
        student_scores = scores.get(s["enrollment_id"], {})
        total = compute_weighted_total(student_scores, components, splits)
        rows.append({
            **s,
            "scores": student_scores,
            "weighted_total": total,
            "passing": total >= PASS_THRESHOLD,
        })
    rows.sort(key=lambda r: r["full_name"])

    return render_template(
        "faculty/grade_registry.html",
        term=term,
        assignments=assignments,
        assignment=assignment,
        components=components,
        rows=rows,
    )


@faculty_bp.route("/grade-entry/export")
@login_required("faculty")
def grade_export():
    assignment_id = request.args.get("assignment_id", type=int)
    assignment = get_assignment_or_404(assignment_id)
    components, ranked = compute_rankings(assignment_id)
    scores = scores_by_enrollment(assignment_id)

    output = io.StringIO()
    writer = csv.writer(output)
    header = ["ID Number", "Full Name"] + [c["component_name"] for c in components] + ["Weighted Total", "Letter Grade"]
    writer.writerow(header)

    for r in ranked:
        row = [r["id_number"], r["full_name"]]
        student_scores = scores.get(r["enrollment_id"], {})
        for c in components:
            score, _max = student_scores.get(c["component_id"], (None, None))
            row.append(score if score is not None else "")
        row.append(r["weighted_total"])
        row.append(r["letter"])
        writer.writerow(row)

    filename = f"{assignment['subject_code']}_{assignment['section']}_grades.csv".replace(" ", "_")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
