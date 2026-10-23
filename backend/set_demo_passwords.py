"""Give the accounts created by database/seed.sql a real password.

seed.sql stores placeholder values (such as 'seed_hash_admin') instead of real password hashes, so
nobody can sign in until a password is set. This script replaces those placeholders with an Argon2
hash of a password you choose. No password is stored in the repository.

    python set_demo_passwords.py              # prompts for a password (input hidden)
    python set_demo_passwords.py --all        # also overwrite accounts that already have a real hash

For non-interactive use, set the LOGITRACK_DEMO_PASSWORD environment variable instead of typing it.
Only for local development: every selected account receives the same password.
"""
import argparse
import getpass
import os
import sys

from auth import hash_password
from database import SessionLocal
from models import User

MIN_LENGTH = 8


def is_placeholder(password_hash: str) -> bool:
    return not str(password_hash or "").startswith("$argon2")


def read_password() -> str:
    from_env = os.getenv("LOGITRACK_DEMO_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("New password for the seeded accounts: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match. Nothing was changed.")
    return first


def set_demo_passwords(password: str, include_real_hashes: bool = False) -> list[str]:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"The password must be at least {MIN_LENGTH} characters.")
    hashed = hash_password(password)
    db = SessionLocal()
    try:
        updated = []
        for user in db.query(User).order_by(User.user_id).all():
            if include_real_hashes or is_placeholder(user.password_hash):
                user.password_hash = hashed
                updated.append(user.username)
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="also overwrite accounts that already have a real password hash")
    args = parser.parse_args()
    try:
        names = set_demo_passwords(read_password(), include_real_hashes=args.all)
    except ValueError as error:
        sys.exit(str(error))
    print(f"Password set for {len(names)} account(s): {', '.join(names) if names else '(none)'}")
