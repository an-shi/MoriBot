"""Backup/restore round-trip and integrity validation tests."""

from __future__ import annotations

import json
import zipfile

import pytest

from moribot.core.accounts import ensure_initial_admin
from moribot.core.backup import BackupError, BackupService
from moribot.core.config import ConfigManager
from moribot.core.db import SQLiteDatabase
from moribot.core.paths import AppPaths
from moribot.core.security import verify_password


async def _prepare_source(tmp_path):
    paths = AppPaths.resolve(tmp_path / "source")
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()

    db = SQLiteDatabase(paths.db_file)
    await db.initialize()
    credentials = await ensure_initial_admin(db, paths)
    await db.dispose()

    plugin_dir = paths.plugin_dir / "echo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text("# test plugin\n", encoding="utf-8")
    media_dir = paths.media_dir / "1"
    media_dir.mkdir(parents=True)
    (media_dir / "sample.png").write_bytes(b"fake-png")
    (paths.log_dir / "moribot.log").write_text("excluded log\n", encoding="utf-8")
    return paths, config, credentials


async def test_backup_roundtrip_restores_every_runtime_file(tmp_path):
    source, source_config, credentials = await _prepare_source(tmp_path)
    archive = tmp_path / "backup.zip"

    info = await BackupService(source).export_to(archive)
    assert info.path == archive
    assert info.includes_database is True
    assert info.file_count >= 4

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "config.json" in names
        assert "moribot.db" in names
        assert "plugins/echo/plugin.py" in names
        assert "media/1/sample.png" in names
        assert "logs/moribot.log" not in names
        assert "initial_admin.txt" not in names

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == "moribot-backup"
        assert manifest["files"]["config.json"]["sha256"]

    target = AppPaths.resolve(tmp_path / "target")
    result = await BackupService(target).import_from(archive)
    assert result.includes_database is True
    assert result.previous_data_dir is None

    restored_config = ConfigManager(target.config_file)
    restored_config.load()
    assert restored_config.jwt_secret == source_config.jwt_secret

    restored_db = SQLiteDatabase(target.db_file)
    try:
        user = await restored_db.get_user_by_username("admin")
        assert user is not None
        assert credentials is not None
        assert verify_password(user.password_hash, credentials.password)
    finally:
        await restored_db.dispose()

    assert (target.plugin_dir / "echo" / "plugin.py").read_text(
        encoding="utf-8"
    ) == "# test plugin\n"
    assert (target.media_dir / "1" / "sample.png").read_bytes() == b"fake-png"
    assert not (target.log_dir / "moribot.log").exists()


async def test_import_rejects_checksum_mismatch(tmp_path):
    source, _, _ = await _prepare_source(tmp_path)
    archive = tmp_path / "backup.zip"
    await BackupService(source).export_to(archive)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as source_zip, zipfile.ZipFile(tampered, "w") as target_zip:
        for member in source_zip.infolist():
            data = source_zip.read(member)
            if member.filename == "config.json":
                data = json.dumps({"config_version": 1}).encode("utf-8")
            target_zip.writestr(member.filename, data)

    with pytest.raises(BackupError):
        await BackupService(AppPaths.resolve(tmp_path / "target")).import_from(tampered)


async def test_import_rejects_path_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    manifest = {
        "format": "moribot-backup",
        "format_version": 1,
        "files": {"../evil.txt": {"size": 4, "sha256": "0" * 64}},
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("../evil.txt", b"evil")

    with pytest.raises(BackupError):
        await BackupService(AppPaths.resolve(tmp_path / "target")).import_from(archive)


async def test_import_requires_config(tmp_path):
    archive = tmp_path / "missing-config.zip"
    manifest = {
        "format": "moribot-backup",
        "format_version": 1,
        "files": {"only.txt": {"size": 4, "sha256": "0" * 64}},
    }
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("only.txt", b"data")

    with pytest.raises(BackupError):
        await BackupService(AppPaths.resolve(tmp_path / "target")).import_from(archive)
