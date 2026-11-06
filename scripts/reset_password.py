"""
Set a correctly bcrypt-hashed password for a user.

Usage:
    python scripts/reset_password.py <username>

Example:
    python scripts/reset_password.py admin
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import execute, query_one  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    new_password = getpass.getpass("New password: ")
    from app.validation import password_error
    error = password_error(new_password)
    if error:
        raise SystemExit(error)
    app = create_app()

    with app.app_context():
        user = query_one("SELECT user_id FROM users WHERE username = :u", {"u": username})
        if not user:
            print(f"No user found with username '{username}'.")
            sys.exit(1)

        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": user["user_id"]},
        )
        print(f"Password updated for '{username}'.")


if __name__ == "__main__":
    main()
