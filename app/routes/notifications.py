"""
Routes for the notification bell shared by admin, faculty, and student
layouts. Not role-specific — any logged-in user can only ever see and
mark-read their own notifications (scoped by user_id in every query).
"""
from functools import wraps

from flask import Blueprint, abort, redirect, request, session, url_for

from . import notifications as notif

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def any_role_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            abort(401)
        return view_func(*args, **kwargs)
    return wrapped


def _safe_redirect_back():
    ref = request.referrer
    if ref and ref.startswith(request.host_url):
        return redirect(ref)
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin.dashboard"))
    if role == "faculty":
        return redirect(url_for("faculty.dashboard"))
    return redirect(url_for("student.dashboard"))


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@any_role_required
def mark_read(notification_id):
    notif.mark_read(notification_id, session["user_id"])
    link = request.form.get("link")
    if link and link.startswith("/"):
        return redirect(link)
    return _safe_redirect_back()


@notifications_bp.route("/read-all", methods=["POST"])
@any_role_required
def mark_all_read():
    notif.mark_all_read(session["user_id"])
    return _safe_redirect_back()
