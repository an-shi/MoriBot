"""Portable data backup and restore.

A backup is a self-describing ZIP archive:

    manifest.json
    config.json
    moribot.db
    plugins/...
    <any future runtime data>

Logs and one-time credentials are intentionally excluded. The database is
snapshotted through SQLite's backup API so a backup can be created while the
server is running. Imports are validated (path safety, checksums, JSON and
SQLite integrity) before the current data directory is swapped out.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from moribot import __version__
from moribot.core.errors import MoriError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.paths import AppPaths

BACKUP_FORMAT = "moribot-backup"
BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "moribot.db"
MAX_IMPORT_BYTES = 10 * 1024**3
MAX_IMPORT_FILES = 100_000

EXCLUDED_TOP_LEVEL = {"logs", "backups", "tmp", "initial_admin.txt", ".gitkeep"}
EXCLUDED_DIR_NAMES = {"__pycache__", ".git", ".DS_Store", "Thumbs.db"}


class BackupError(MoriError):
    """Raised when an export or import cannot be completed safely."""

    def __init__(
        self,
        message_key: str,
        *,
        locale: str = DEFAULT_LOCALE,
        status_code: int = 400,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            translate(message_key, locale, **kwargs),
            status_code=status_code,
        )
        self.message_key = message_key


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Metadata about a freshly created backup."""

    path: Path
    size: int
    created_at: str
    file_count: int
    includes_database: bool


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of a successful import."""

    imported_files: int
    includes_database: bool
    previous_data_dir: Path | None


def default_backup_filename(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).astimezone().strftime("%Y%m%d-%H%M%S")
    return f"moribot-backup-{stamp}.zip"


class BackupService:
    """Create and restore portable MoriBot data archives."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    async def export_to(self, output: Path, *, locale: str = DEFAULT_LOCALE) -> BackupInfo:
        """Create a backup archive without blocking the event loop."""
        try:
            return await asyncio.to_thread(self._export_sync, output, locale)
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("backup.export_failed", locale=locale) from exc

    async def import_from(
        self,
        archive: Path,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> ImportResult:
        """Validate and install a backup archive without blocking the loop."""
        try:
            return await asyncio.to_thread(self._import_sync, archive, locale)
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("backup.import_failed", locale=locale) from exc

    # -- Export ----------------------------------------------------------

    def _export_sync(self, output: Path, locale: str) -> BackupInfo:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC).isoformat()
        data_dir = self.paths.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        files: list[tuple[Path, str]] = []
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(data_dir)
            if self._is_excluded(relative):
                continue
            if path.name in {
                DATABASE_NAME,
                "moribot.db-wal",
                "moribot.db-shm",
                "moribot.db-journal",
            }:
                continue
            if path.resolve() == output:
                continue
            files.append((path, relative.as_posix()))

        with tempfile.TemporaryDirectory(prefix="moribot-backup-") as temp_dir:
            database_snapshot: Path | None = None
            if self.paths.db_file.is_file():
                database_snapshot = Path(temp_dir) / DATABASE_NAME
                self._snapshot_database(self.paths.db_file, database_snapshot)

            manifest_files: dict[str, dict[str, Any]] = {}
            includes_database = database_snapshot is not None

            try:
                with zipfile.ZipFile(
                    output,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as archive:
                    for source, arcname in files:
                        manifest_files[arcname] = self._write_member(archive, source, arcname)
                    if database_snapshot is not None:
                        manifest_files[DATABASE_NAME] = self._write_member(
                            archive,
                            database_snapshot,
                            DATABASE_NAME,
                        )

                    manifest = {
                        "format": BACKUP_FORMAT,
                        "format_version": BACKUP_FORMAT_VERSION,
                        "app_version": __version__,
                        "created_at": created_at,
                        "excluded": sorted(EXCLUDED_TOP_LEVEL),
                        "database": DATABASE_NAME if includes_database else None,
                        "files": manifest_files,
                    }
                    archive.writestr(
                        MANIFEST_NAME,
                        json.dumps(manifest, ensure_ascii=False, indent=2),
                    )
            except Exception:
                output.unlink(missing_ok=True)
                raise

        try:
            os.chmod(output, 0o600)
        except OSError:
            pass

        return BackupInfo(
            path=output,
            size=output.stat().st_size,
            created_at=created_at,
            file_count=len(manifest_files),
            includes_database=includes_database,
        )

    def _is_excluded(self, relative: Path) -> bool:
        parts = relative.parts
        if not parts:
            return True
        if parts[0] in EXCLUDED_TOP_LEVEL:
            return True
        return any(part in EXCLUDED_DIR_NAMES for part in parts)

    @staticmethod
    def _write_member(archive: zipfile.ZipFile, source: Path, arcname: str) -> dict[str, Any]:
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as reader, archive.open(arcname, "w") as writer:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                writer.write(chunk)
        return {"size": size, "sha256": digest.hexdigest()}

    @staticmethod
    def _snapshot_database(source: Path, destination: Path) -> None:
        """Use SQLite's online backup API for a consistent snapshot."""
        source_connection = sqlite3.connect(source)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()

    # -- Import ----------------------------------------------------------

    def _import_sync(self, archive_path: Path, locale: str) -> ImportResult:
        archive_path = archive_path.expanduser().resolve()
        if not archive_path.is_file():
            raise BackupError("backup.file_not_found", locale=locale)

        try:
            archive = zipfile.ZipFile(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise BackupError("backup.invalid_archive", locale=locale) from exc

        with archive:
            manifest = self._read_manifest(archive, locale)
            expected = self._validate_members(archive, manifest, locale)
            includes_database = DATABASE_NAME in expected
            temp_dir = self._extract_to_temp(archive, expected, locale)

        try:
            config_path = temp_dir / "config.json"
            self._validate_config(config_path, locale)
            if includes_database:
                self._validate_database(temp_dir / DATABASE_NAME, locale)

            previous = self._install(temp_dir, locale)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        return ImportResult(
            imported_files=len(expected),
            includes_database=includes_database,
            previous_data_dir=previous,
        )

    def _read_manifest(self, archive: zipfile.ZipFile, locale: str) -> dict[str, Any]:
        if len(archive.infolist()) > MAX_IMPORT_FILES + 1:
            raise BackupError("backup.invalid_archive", locale=locale)
        try:
            manifest_info = archive.getinfo(MANIFEST_NAME)
            if manifest_info.file_size > 5 * 1024 * 1024:
                raise BackupError("backup.invalid_manifest", locale=locale)
            raw = archive.read(manifest_info)
            manifest = json.loads(raw.decode("utf-8"))
        except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("backup.invalid_manifest", locale=locale) from exc

        if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
            raise BackupError("backup.invalid_manifest", locale=locale)
        try:
            format_version = int(manifest.get("format_version", -1))
        except (TypeError, ValueError) as exc:
            raise BackupError("backup.invalid_manifest", locale=locale) from exc
        if format_version != BACKUP_FORMAT_VERSION:
            raise BackupError("backup.unsupported_format", locale=locale)

        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise BackupError("backup.invalid_manifest", locale=locale)
        return manifest

    def _validate_members(
        self,
        archive: zipfile.ZipFile,
        manifest: dict[str, Any],
        locale: str,
    ) -> dict[str, zipfile.ZipInfo]:
        expected: dict[str, zipfile.ZipInfo] = {}
        files: dict[str, Any] = manifest["files"]
        total_size = 0

        if len(files) > MAX_IMPORT_FILES:
            raise BackupError("backup.invalid_archive", locale=locale)

        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            normalized = self._safe_member_name(info.filename, locale)
            if normalized == MANIFEST_NAME:
                continue
            if normalized in by_name:
                raise BackupError("backup.invalid_archive", locale=locale)
            by_name[normalized] = info

        for raw_name, metadata in files.items():
            if not isinstance(raw_name, str) or not isinstance(metadata, dict):
                raise BackupError("backup.invalid_manifest", locale=locale)
            name = self._safe_member_name(raw_name, locale)
            info = by_name.get(name)
            if info is None:
                raise BackupError("backup.invalid_archive", locale=locale)
            self._reject_symlink(info, locale)
            if info.file_size < 0 or int(metadata.get("size", -1)) != info.file_size:
                raise BackupError("backup.invalid_archive", locale=locale)
            total_size += info.file_size
            if total_size > MAX_IMPORT_BYTES:
                raise BackupError("backup.invalid_archive", locale=locale)
            expected[name] = info

        # Every payload member must be declared in the manifest.
        if set(by_name) != set(expected):
            raise BackupError("backup.invalid_archive", locale=locale)
        if "config.json" not in expected:
            raise BackupError("backup.missing_config", locale=locale)
        return expected

    @staticmethod
    def _safe_member_name(raw_name: str, locale: str) -> str:
        name = raw_name.replace("\\", "/")
        pure = PurePosixPath(name)
        if (
            not name
            or name.startswith("/")
            or any(part in {"", ".", ".."} for part in pure.parts)
            or (pure.parts and len(pure.parts[0]) >= 2 and pure.parts[0][1] == ":")
        ):
            raise BackupError("backup.unsafe_path", locale=locale)
        return pure.as_posix()

    @staticmethod
    def _reject_symlink(info: zipfile.ZipInfo, locale: str) -> None:
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise BackupError("backup.unsafe_path", locale=locale)

    def _extract_to_temp(
        self,
        archive: zipfile.ZipFile,
        expected: dict[str, zipfile.ZipInfo],
        locale: str,
    ) -> Path:
        self.paths.data_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(
            tempfile.mkdtemp(
                prefix=".moribot-import-",
                dir=self.paths.data_dir.parent,
            )
        )
        try:
            manifest_files = self._read_manifest(archive, locale)["files"]
            normalized_files = {
                self._safe_member_name(str(name), locale): metadata
                for name, metadata in manifest_files.items()
            }
            for name, info in expected.items():
                destination = temp_dir / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(info) as reader, destination.open("wb") as writer:
                    while chunk := reader.read(1024 * 1024):
                        digest.update(chunk)
                        writer.write(chunk)
                if digest.hexdigest() != str(normalized_files[name].get("sha256", "")):
                    raise BackupError(
                        "backup.checksum_mismatch",
                        locale=locale,
                        path=name,
                    )
                if name in {"config.json", DATABASE_NAME}:
                    try:
                        os.chmod(destination, 0o600)
                    except OSError:
                        pass
            return temp_dir
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    @staticmethod
    def _validate_config(config_path: Path, locale: str) -> None:
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError("backup.missing_config", locale=locale) from exc
        if not isinstance(raw, dict):
            raise BackupError("backup.missing_config", locale=locale)

    @staticmethod
    def _validate_database(database_path: Path, locale: str) -> None:
        connection = sqlite3.connect(database_path)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupError("backup.database_corrupt", locale=locale) from exc
        finally:
            connection.close()
        if not result or result[0] != "ok":
            raise BackupError("backup.database_corrupt", locale=locale)

    def _install(self, temp_dir: Path, locale: str) -> Path | None:
        data_dir = self.paths.data_dir
        if not data_dir.exists():
            os.replace(temp_dir, data_dir)
            return None

        if any(data_dir.iterdir()):
            stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
            previous = data_dir.with_name(f"{data_dir.name}.pre-import-{stamp}")
            os.replace(data_dir, previous)
            try:
                os.replace(temp_dir, data_dir)
            except Exception:
                os.replace(previous, data_dir)
                raise
            return previous

        shutil.rmtree(data_dir, ignore_errors=True)
        os.replace(temp_dir, data_dir)
        return None
