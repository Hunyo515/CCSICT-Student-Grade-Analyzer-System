from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import hash_password, verify_password
from ..db import execute, execute_returning_id, query_all, query_one
from ..notifications import notify_many

auth_bp = Blueprint("auth", __name__)

ROLE_DASHBOARD = {
    "admin": "admin.dashboard",
    "faculty": "faculty.dashboard",
    "student": "student.dashboard",
}

ROLE_LABELS = {
    "admin": "Admin",
    "faculty": "Faculty",
    "student": "Student",
}


@auth_bp.route("/")
def select_role():
    if session.get("user_id") and session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    return render_template("auth/select_role.html")


@auth_bp.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ROLE_DASHBOARD:
        return redirect(url_for("auth.select_role"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = query_one(
            """
            SELECT user_id, username, password_hash, role, full_name, status
            FROM users
            WHERE username = :username AND role = :role
            """,
            {"username": username, "role": role},
        )

        if not user or user["status"] != "ACTIVE" or not verify_password(password, user["password_hash"]):
            flash("Invalid username or password.", "error")
            return render_template("auth/login.html", role=role, role_label=ROLE_LABELS[role])

        session.clear()
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]

        if role == "faculty":
            teacher = query_one("SELECT teacher_id FROM teachers WHERE user_id = :user_id", {"user_id": user["user_id"]})
            if teacher:
                session["teacher_id"] = teacher["teacher_id"]
        elif role == "student":
            student = query_one("SELECT student_id FROM students WHERE user_id = :user_id", {"user_id": user["user_id"]})
            if student:
                session["student_id"] = student["student_id"]

        return redirect(url_for(ROLE_DASHBOARD[role]))

    return render_template("auth/login.html", role=role, role_label=ROLE_LABELS[role])


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.select_role"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        id_number = request.form.get("id_number", "").strip().upper()
        year_level = request.form.get("year_level", "").strip()
        section = request.form.get("section", "").strip()
        program = request.form.get("program", "").strip()
        email = request.form.get("email", "").strip()
        sex = request.form.get("sex", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form_data = request.form.to_dict()

        if not all([first_name, last_name, id_number, year_level, section, program, email, password]):
            flash("Please fill in all required fields.", "error")
            return render_template("auth/registration.html", form=form_data)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth/registration.html", form=form_data)

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/registration.html", form=form_data)

        if query_one("SELECT student_id FROM students WHERE id_number = :i", {"i": id_number}):
            flash(f"ID number {id_number} is already registered.", "error")
            return render_template("auth/registration.html", form=form_data)

        username = id_number.lower()
        if query_one("SELECT user_id FROM users WHERE username = :u", {"u": username}):
            flash("An account with this ID already exists.", "error")
            return render_template("auth/registration.html", form=form_data)

        full_name = f"{first_name} {last_name}"
        user_id = execute_returning_id(
            """
            INSERT INTO users (username, password_hash, role, full_name, email, status)
            VALUES (:username, :pw, 'student', :full_name, :email, 'ACTIVE')
            RETURNING user_id INTO :out_id
            """,
            {"username": username, "pw": hash_password(password), "full_name": full_name, "email": email},
        )
        execute(
            """
            INSERT INTO students (user_id, id_number, program, year_level, section, sex, enrollment_type, status)
            VALUES (:user_id, :id_number, :program, :year_level, :section, :sex, 'REGULAR', 'ACTIVE')
            """,
            {"user_id": user_id, "id_number": id_number, "program": program, "year_level": year_level, "section": section, "sex": sex},
        )

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login", role="student"))

    return render_template("auth/registration.html", form={})


@auth_bp.route("/forgot-password/<role>", methods=["GET", "POST"])
def forgot_password(role):
    if role not in ROLE_DASHBOARD:
        return redirect(url_for("auth.select_role"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = query_one(
            "SELECT user_id, full_name FROM users WHERE username = :u AND role = :r",
            {"u": username, "r": role},
        )
        if user:
            admins = query_all("SELECT user_id FROM users WHERE role = 'admin' AND status = 'ACTIVE'")
            notify_many(
                [a["user_id"] for a in admins],
                f"Password reset requested by {user['full_name']} ({ROLE_LABELS[role]}, username: {username}).",
                link=url_for("admin.settings"),
            )
        # Always show the same message whether or not the account exists,
        # so this can't be used to check which usernames are registered.
        flash("If that account exists, your system administrator has been notified and will reach out to reset your password.", "success")
        return redirect(url_for("auth.login", role=role))

    return render_template("auth/forgot_password.html", role=role, role_label=ROLE_LABELS[role])
