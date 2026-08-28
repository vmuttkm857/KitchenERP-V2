import argparse
import getpass

from pydantic import ValidationError

from app.db.session import SessionLocal
from app.domains.users.exceptions import UsernameAlreadyExistsError
from app.domains.users.schemas import CreateUserCommand
from app.domains.users.service import UserService


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first KitchenERP administrator")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 1

    try:
        command = CreateUserCommand(
            username=args.username,
            password=password,
            display_name=args.display_name,
            role="admin",
        )
    except ValidationError as exc:
        print("Invalid admin details:")
        for error in exc.errors(include_url=False, include_input=False):
            print(f"- {error['msg']}")
        return 1

    session = SessionLocal()
    try:
        user = UserService(session).create_user(command)
    except UsernameAlreadyExistsError:
        print("Username already exists.")
        return 1
    finally:
        session.close()

    print(f"Administrator '{user.username}' created successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
