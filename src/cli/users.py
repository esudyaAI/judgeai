"""Provision local users (administrators included) without command-line passwords."""

import argparse
import asyncio
import getpass

from sqlalchemy import delete, select, update

from src.db.auth import User, UserSession
from src.db.models import Chat
from src.db.session import async_session_factory
from src.services.auth import hash_password, normalize_username


async def run(args):
    username = normalize_username(args.username)
    encoded = None
    if args.command == "create":
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            raise ValueError("Passwords do not match")
        encoded = await hash_password(password)
    async with async_session_factory() as db, db.begin():
        user = await db.scalar(select(User).where(User.username == username))
        if args.command == "create":
            if user is not None:
                raise ValueError("Username already exists")
            db.add(User(username=username, password_hash=encoded, is_admin=args.admin))
        elif args.command == "disable":
            if user is None:
                raise ValueError("User not found")
            user.is_active = False
            await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        else:
            if not args.confirm_ownership:
                raise ValueError("Explicit --confirm-ownership is required")
            if user is None or not user.is_active:
                raise ValueError("Active destination user required")
            legacy = await db.scalar(select(User).where(User.username == "__legacy_locked__"))
            if legacy is None:
                raise ValueError("Legacy account not found")
            result = await db.execute(
                update(Chat)
                .where(Chat.id.in_(args.case_id), Chat.owner_id == legacy.id)
                .values(owner_id=user.id)
            )
            if result.rowcount != len(set(args.case_id)):
                raise ValueError(
                    "Some cases are missing or are not owned by the locked legacy account"
                )
    print("Account operation completed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--admin", action="store_true")
    disable = commands.add_parser("disable")
    disable.add_argument("--username", required=True)
    assign = commands.add_parser("assign-legacy")
    assign.add_argument("--username", required=True)
    assign.add_argument("--case-id", action="append", type=int, required=True)
    assign.add_argument("--confirm-ownership", action="store_true")
    try:
        asyncio.run(run(parser.parse_args()))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
