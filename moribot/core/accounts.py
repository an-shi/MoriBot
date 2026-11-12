"""First-run administrator bootstrap.

The initial password is generated locally, printed once to the logs and saved
to ``data/initial_admin.txt`` so a headless deployment is not locked out. The
file is removed after the account password changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger

from .db import BaseDatabase
from .i18n import DEFAULT_LOCALE, translate
from .paths import AppPaths
from .security import generate_password, hash_password

INITIAL_ADMIN_USERNAME = "admin"
INITIAL_CREDENTIALS_FILENAME = "initial_admin.txt"


@dataclass(frozen=True, slots=True)
class AdminCredentials:
    """The one-time credentials created during bootstrap or reset."""

    username: str
    password: str
    created: bool


def _credentials_path(paths: AppPaths):
    return paths.data_dir / INITIAL_CREDENTIALS_FILENAME


def _write_credentials(
    paths: AppPaths,
    credentials: AdminCredentials,
    locale: str = DEFAULT_LOCALE,
) -> None:
    path = _credentials_path(paths)
    timestamp = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    title = translate("accounts.file_title", locale)
    account_line = translate(
        "accounts.file_line",
        locale,
        username=credentials.username,
        password=credentials.password,
        timestamp=timestamp,
    )
    hint = translate("accounts.file_hint", locale)
    content = f"{title}\n{'=' * 30}\n{account_line}\n\n{hint}\n"
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # chmod is not meaningful on every Windows filesystem; the file still
        # lives inside the user-controlled data directory.
        pass


def _log_credentials(
    credentials: AdminCredentials,
    paths: AppPaths,
    locale: str = DEFAULT_LOCALE,
) -> None:
    logger.warning(
        translate(
            "accounts.log_block",
            locale,
            title=translate("accounts.log_title", locale),
            username=credentials.username,
            password=credentials.password,
            file_label=translate("accounts.credentials_file", locale),
            path=_credentials_path(paths),
            hint=translate("accounts.log_hint", locale),
        )
    )


async def ensure_initial_admin(
    db: BaseDatabase,
    paths: AppPaths,
    locale: str = DEFAULT_LOCALE,
) -> AdminCredentials | None:
    """Create the first administrator when the database has no accounts.

    Args:
        db: Initialized database.
        paths: Runtime paths used for the credentials file.
        locale: Language used for the one-time credential output.

    Returns:
        Generated credentials when an account was created, otherwise ``None``.
    """
    if await db.count_users() > 0:
        return None

    password = generate_password()
    user = await db.create_user(
        username=INITIAL_ADMIN_USERNAME,
        password_hash=hash_password(password),
        display_name="Administrator",
        role="admin",
    )
    credentials = AdminCredentials(username=user.username, password=password, created=True)
    _write_credentials(paths, credentials, locale)
    _log_credentials(credentials, paths, locale)
    return credentials


async def reset_admin_password(
    db: BaseDatabase,
    paths: AppPaths,
    locale: str = DEFAULT_LOCALE,
) -> AdminCredentials:
    """Reset the first administrator's password and print new credentials.

    Args:
        db: Initialized database.
        paths: Runtime paths used for the credentials file.
        locale: Language used for the one-time credential output.

    Returns:
        The freshly generated credentials.
    """
    password = generate_password()
    user = await db.get_first_admin()

    if user is None:
        created = await db.create_user(
            username=INITIAL_ADMIN_USERNAME,
            password_hash=hash_password(password),
            display_name="Administrator",
            role="admin",
        )
        credentials = AdminCredentials(username=created.username, password=password, created=True)
    else:
        updated = await db.update_user_password(user.id, hash_password(password))
        username = updated.username if updated is not None else user.username
        credentials = AdminCredentials(username=username, password=password, created=False)

    _write_credentials(paths, credentials, locale)
    _log_credentials(credentials, paths, locale)
    return credentials


def delete_initial_credentials(paths: AppPaths) -> None:
    """Remove the plaintext credentials file after a password change."""
    try:
        _credentials_path(paths).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove the initial credentials file.")
