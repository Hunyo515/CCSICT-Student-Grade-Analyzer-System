"""
Set a correctly bcrypt-hashed password for a user.

Usage:
<<<<<<< HEAD
    python scripts/reset_password.py <username>

Example:
    python scripts/reset_password.py admin
"""
import getpass
=======
    python scripts/reset_password.py <username> <new_password>

Example:
    python scripts/reset_password.py admin password123
"""
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import execute, query_one  # noqa: E402


def main():
<<<<<<< HEAD
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    new_password = getpass.getpass("New password: ")
    from app.validation import password_error
    error = password_error(new_password)
    if error:
        raise SystemExit(error)
=======
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    username, new_password = sys.argv[1], sys.argv[2]
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
