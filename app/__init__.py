from flask import Flask

from config import Config

from .db import init_pool, register_teardown


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    @app.context_processor
    def inject_globals():
        from .auth import current_user
        from . import notifications as notif
        from .db import query_all

        user = current_user()
        nav_notifications = []
        nav_unread_count = 0
        nav_all_terms = []
        if user:
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
            "current_user": user,
            "nav_notifications": nav_notifications,
            "nav_unread_count": nav_unread_count,
            "nav_all_terms": nav_all_terms,
        }

    return app
