"""Password hashing and role-based access-control helpers."""
from functools import wraps

import bcrypt
from flask import abort, flash, redirect, session, url_for


def hash_password(plain_password: str) -> str:
<<<<<<< HEAD
    from .validation import password_error
    error = password_error(plain_password)
    if error:
        raise ValueError(error)
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
<<<<<<< HEAD
        if len(plain_password.encode("utf-8")) > 72:
            return False
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def login_required(role: str):
    """
    Decorator factory: @login_required("admin") guards a view so only an
    authenticated session with that role may access it.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if session.get("role") != role or not session.get("user_id"):
                flash("Please log in to continue.", "error")
                return redirect(url_for("auth.login", role=role))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def current_user():
    if not session.get("user_id"):
        return None
    return {
        "user_id": session["user_id"],
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
    }
