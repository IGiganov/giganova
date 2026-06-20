"""Generate a bcrypt hash for AUTH_PASSWORD_HASH.

Usage:
    python -m app.hash_password            # prompts securely (recommended)
    python -m app.hash_password "secret"   # password as an argument
"""
import getpass
import sys

from app.security import hash_password


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            raise SystemExit(1)

    if not password:
        print("Password cannot be empty.")
        raise SystemExit(1)

    digest = hash_password(password)
    print("\nAdd this line to your .env (keep it secret):\n")
    print(f"AUTH_PASSWORD_HASH={digest}")


if __name__ == "__main__":
    main()
