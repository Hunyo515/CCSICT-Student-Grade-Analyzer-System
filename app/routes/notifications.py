"""
Routes for the notification bell shared by admin, faculty, and student
layouts. Not role-specific — any logged-in user can only ever see and
mark-read their own notifications (scoped by user_id in every query).
"""
from functools import wraps

from flask import Blueprint, abort, redirect, request, session, url_for

from .. import notifications as notif

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
    # Read the destination from the owned notification, never from submitted data.
    from ..db import query_one
    from urllib.parse import urlsplit, unquote
    row = query_one("SELECT link FROM notifications WHERE notification_id=:id AND user_id=:user_key", {"id": notification_id, "user_key": session["user_id"]})
    link = row.get("link") if row else None
    normalized = unquote(link or "")
    if normalized.startswith("/") and not normalized.startswith("//") and "\\" not in normalized and not urlsplit(normalized).netloc:
        return redirect(link)
    return _safe_redirect_back()


@notifications_bp.route("/read-all", methods=["POST"])
@any_role_required
def mark_all_read():
    notif.mark_all_read(session["user_id"])
    return _safe_redirect_back()


@notifications_bp.route('/delete',methods=['POST'])
@any_role_required
def delete_selected():
    raw=request.form.getlist('notification_id')
    if not raw or len(raw)>200 or any(not value.isdigit() or len(value)>15 or int(value)<=0 for value in raw):
        abort(400,description='Select notifications to delete.')
    from ..db import execute
    ids=sorted({int(value) for value in raw});params={'user_id':session['user_id']}
    params.update({f'n{i}':value for i,value in enumerate(ids)})
    binds=','.join(f':n{i}' for i in range(len(ids)))
    execute(f'DELETE FROM notifications WHERE user_id=:user_id AND notification_id IN ({binds})',params)
    return _safe_redirect_back()
