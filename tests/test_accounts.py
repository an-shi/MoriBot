"""Administrator bootstrap and password reset tests."""

from __future__ import annotations

from moribot.core.accounts import ensure_initial_admin, reset_admin_password
from moribot.core.db import SQLiteDatabase
from moribot.core.paths import AppPaths
from moribot.core.security import verify_password


async def test_initial_admin_is_created_once_and_reset_rotates_password(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    db = SQLiteDatabase(paths.db_file)
    await db.initialize()

    try:
        first = await ensure_initial_admin(db, paths)
        assert first is not None
        assert first.username == "admin"
        assert (paths.data_dir / "initial_admin.txt").is_file()

        second = await ensure_initial_admin(db, paths)
        assert second is None

        user = await db.get_user_by_username("admin")
        assert user is not None
        assert verify_password(user.password_hash, first.password)

        rotated = await reset_admin_password(db, paths)
        refreshed = await db.get_user_by_username("admin")
        assert refreshed is not None
        assert refreshed.token_version == user.token_version + 1
        assert verify_password(refreshed.password_hash, rotated.password)
        assert not verify_password(refreshed.password_hash, first.password)
    finally:
        await db.dispose()
