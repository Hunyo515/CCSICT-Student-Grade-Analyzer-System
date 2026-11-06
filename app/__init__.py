<<<<<<< HEAD
from urllib.parse import urlsplit

from flask import Flask, request, session
=======
from flask import Flask
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423

from config import Config

from .db import init_pool, register_teardown


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

<<<<<<< HEAD
    from .security import init_security, protect_request, validate_session
    from .validation import validate_request
    init_security(app)
    from .email_otp import init_otp
    with app.app_context():
        init_otp()
        from .university_accounts import init_credentials
        init_credentials()
    app.before_request(validate_session)
    app.before_request(protect_request)
    app.before_request(validate_request)

    from flask import render_template, g
    from werkzeug.exceptions import HTTPException
    @app.errorhandler(HTTPException)
    def input_error(error):
        g.error_page = True
        response = error.get_response()
        back_url = request.referrer
        if back_url:
            referrer = urlsplit(back_url)
            if referrer.scheme not in ("http", "https") or referrer.netloc != request.host:
                back_url = None
        response.set_data(render_template("error.html", error=error, back_url=back_url))
        response.content_type = "text/html; charset=utf-8"
        return response

    import oracledb
    import csv
    from werkzeug.exceptions import BadRequest
    @app.errorhandler(csv.Error)
    def invalid_csv(error):
        return input_error(BadRequest("The CSV could not be parsed. Check its quoting, columns, and field lengths."))

    @app.errorhandler(oracledb.IntegrityError)
    def integrity_error(error):
        g.error_page = True
        return render_template("error.html", error=BadRequest("A record already exists, a referenced record is missing, or this record is still in use. Check your input and try again.")), 400

    @app.errorhandler(oracledb.DatabaseError)
    def database_unavailable(error):
        from werkzeug.exceptions import ServiceUnavailable
        app.logger.error("Database operation failed (%s)", type(error).__name__)
        return input_error(ServiceUnavailable("The database is temporarily unavailable. Please try again later."))

    @app.errorhandler(500)
    def unexpected_error(error):
        from werkzeug.exceptions import InternalServerError
        return input_error(InternalServerError("Something went wrong. Please try again or contact your administrator."))

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if response.mimetype == "text/html" or session.get("user_id"):
            response.headers["Cache-Control"] = "no-store"
        return response

=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    init_pool(app)
    register_teardown(app)

    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.faculty import faculty_bp
    from .routes.student import student_bp
    from .routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(notifications_bp)
<<<<<<< HEAD
    from .routes.workspace import workspace_bp
    app.register_blueprint(workspace_bp)
    from .routes.srs import srs_bp
    app.register_blueprint(srs_bp)
    from .routes.university import university_bp
    app.register_blueprint(university_bp)
    from .workspace_access import install_workspace_routes
    install_workspace_routes(app)

    @app.context_processor
    def inject_globals():
        from .curriculum import PROGRAM_NAMES, PROGRAM_ALIASES, canonical_program
=======

    @app.context_processor
    def inject_globals():
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        from .auth import current_user
        from . import notifications as notif
        from .db import query_all

        user = current_user()
<<<<<<< HEAD
        student_photo_url=None
        if user and user.get('role')=='student':
            from .profile_photos import photo_path
            from flask import url_for
            avatar=photo_path(user['user_id'])
            if avatar.is_file():student_photo_url=url_for('student.profile_photo',v=avatar.stat().st_mtime_ns)
        nav_notifications = []
        nav_unread_count = 0
        nav_all_terms = []
        if user and not getattr(g, "error_page", False):
=======
        nav_notifications = []
        nav_unread_count = 0
        nav_all_terms = []
        if user:
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
            nav_notifications = notif.recent(user["user_id"])
            nav_unread_count = notif.unread_count(user["user_id"])

            terms = query_all(
                "SELECT term_id, school_year, semester, is_active FROM school_terms ORDER BY term_id DESC"
            )
            active = next((t for t in terms if t["is_active"]), None)
            active_id = active["term_id"] if active else None
            for t in terms:
                if t["is_active"]:
                    t["state"] = "active"
                elif active_id is not None and t["term_id"] > active_id:
                    t["state"] = "upcoming"
                else:
                    t["state"] = "completed"
            nav_all_terms = terms

        return {
<<<<<<< HEAD
            "curriculum_programs": PROGRAM_NAMES,
            "program_aliases": PROGRAM_ALIASES,
            "canonical_program": canonical_program,
            "current_user": user,
            "student_photo_url":student_photo_url,
=======
            "current_user": user,
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
            "nav_notifications": nav_notifications,
            "nav_unread_count": nav_unread_count,
            "nav_all_terms": nav_all_terms,
        }

    return app
