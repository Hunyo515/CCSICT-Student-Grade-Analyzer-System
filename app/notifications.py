"""
Shared notification helpers used by all three portals (admin, faculty,
student). A notification always belongs to one users.user_id row, so the
same table and helpers work regardless of role.
"""
from flask import current_app
from .db import execute, query_all, query_one


def notify(user_id, message, link=None):
    """Create one notification for a single user. Never raises on its own —
    a notification failing to send should never block the action that
    triggered it (e.g. publishing grades)."""
    if not user_id:
        return
    try:
        execute(
            "INSERT INTO notifications (user_id, message, link) VALUES (:user_id, :msg, :link)",
            {"user_id": user_id, "msg": message.encode("utf-8")[:255].decode("utf-8", errors="ignore"), "link": link},
        )
    except Exception as error:
        current_app.logger.warning("Notification could not be stored (%s)", type(error).__name__)


def notify_many(user_ids, message, link=None):
    for uid in user_ids:
        notify(uid, message, link)


def unread_count(user_id):
    row = query_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = :user_id AND is_read = 'N'",
        {"user_id": user_id},
    )
    return row["c"] if row else 0


def recent(user_id, limit=8):
    limit = int(limit)
    return query_all(
        f"""
        SELECT notification_id, message, link, is_read, created_at
        FROM notifications
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        FETCH FIRST {limit} ROWS ONLY
        """,
        {"user_id": user_id},
    )


def mark_read(notification_id, user_id):
    execute(
        "UPDATE notifications SET is_read = 'Y' WHERE notification_id = :notification_id AND user_id = :user_id",
        {"notification_id": notification_id, "user_id": user_id},
    )


def mark_all_read(user_id):
    execute(
        "UPDATE notifications SET is_read = 'Y' WHERE user_id = :user_id AND is_read = 'N'",
        {"user_id": user_id},
    )
