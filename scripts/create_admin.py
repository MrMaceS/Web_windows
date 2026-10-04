"""
scripts/create_admin.py
Создаёт первого администратора админки. Не запускается автоматически и не
входит в Alembic-миграции — учётные данные администратора не должны
появляться в истории миграций/git.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, AdminUser, init_db  # noqa: E402
from security import hash_password  # noqa: E402


def main() -> None:
    init_db()

    username = input("Логин администратора: ").strip()
    if not username:
        print("Логин не может быть пустым.")
        sys.exit(1)

    password = getpass.getpass("Пароль (не менее 8 символов): ")
    if len(password) < 8:
        print("Пароль слишком короткий.")
        sys.exit(1)
    password_confirm = getpass.getpass("Повторите пароль: ")
    if password != password_confirm:
        print("Пароли не совпадают.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(AdminUser).filter(AdminUser.username == username).first()
        if existing is not None:
            print(f"Пользователь '{username}' уже существует.")
            sys.exit(1)

        user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Администратор '{username}' создан.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
