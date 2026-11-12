"""Command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from loguru import logger

from moribot import __version__
from moribot.core.accounts import reset_admin_password
from moribot.core.backup import BackupService, default_backup_filename
from moribot.core.config import ConfigManager
from moribot.core.db import SQLiteDatabase
from moribot.core.errors import MoriError
from moribot.core.i18n import normalize_locale, translate
from moribot.core.logging import LogBroker, setup_logging
from moribot.core.paths import AppPaths

BANNER = r"""
 __  __            _ ____        _
|  \/  | ___  _ __(_) __ )  ___ | |_
| |\/| |/ _ \| '__| |  _ \ / _ \| __|
| |  | | (_) | |  | | |_) | (_) | |_
|_|  |_|\___/|_|  |_|____/ \___/ \__|
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moribot",
        description="MoriBot - a modular AI assistant control plane",
    )
    parser.add_argument("--host", default=None, help="Override the dashboard bind host")
    parser.add_argument("--port", type=int, default=None, help="Override the dashboard port")
    parser.add_argument("--data-dir", default=None, help="Directory for config, database and logs")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Generate a new administrator password and print it",
    )
    parser.add_argument("--log-level", default=None, help="Override the configured log level")
    parser.add_argument(
        "--ssl-certfile",
        default=None,
        help="TLS certificate for direct HTTPS (reverse proxy preferred)",
    )
    parser.add_argument("--ssl-keyfile", default=None, help="TLS private key for direct HTTPS")
    parser.add_argument(
        "--forwarded-allow-ips",
        default=None,
        help="Trust X-Forwarded-* headers only from these proxy addresses",
    )
    parser.add_argument(
        "--no-proxy-headers",
        action="store_true",
        help="Ignore proxy forwarding headers",
    )
    parser.add_argument("--version", action="version", version=f"MoriBot {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    backup_parser = subparsers.add_parser(
        "backup",
        help="Export or import a portable data archive",
    )
    backup_subparsers = backup_parser.add_subparsers(
        dest="backup_command",
        required=True,
    )

    export_parser = backup_subparsers.add_parser("export", help="Create a data archive")
    export_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Archive path (default: ./moribot-backup-<timestamp>.zip)",
    )

    import_parser = backup_subparsers.add_parser("import", help="Restore a data archive")
    import_parser.add_argument("archive", help="Archive to import")
    import_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the interactive confirmation",
    )
    return parser


async def _reset_password(paths: AppPaths, locale: str) -> None:
    db = SQLiteDatabase(paths.db_file)
    await db.initialize()
    try:
        await reset_admin_password(db, paths, locale)
    finally:
        await db.dispose()


def _backup_locale(paths: AppPaths) -> str:
    env_locale = os.environ.get("MORIBOT_LOCALE")
    if env_locale:
        return normalize_locale(env_locale)
    try:
        raw = json.loads(paths.config_file.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            bot = raw.get("bot")
            if isinstance(bot, dict):
                return normalize_locale(str(bot.get("locale", "zh-CN")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return normalize_locale("zh-CN")


def _run_backup_command(args: argparse.Namespace, paths: AppPaths) -> None:
    locale = _backup_locale(paths)
    service = BackupService(paths)

    if args.backup_command == "export":
        # Make sure a fresh data directory still produces a valid archive
        # containing config.json (and its generated JWT secret).
        ConfigManager(paths.config_file).load()
        output = (
            Path(args.output).expanduser()
            if args.output
            else Path.cwd() / default_backup_filename()
        )
        info = asyncio.run(service.export_to(output, locale=locale))
        print(translate("backup.export_done", locale, path=info.path))
        print(f"files: {info.file_count}, size: {info.size} bytes")
        return

    archive = Path(args.archive).expanduser()
    if not archive.is_file():
        raise MoriError(translate("backup.file_not_found", locale), status_code=404)

    if not args.yes:
        if not sys.stdin.isatty():
            raise MoriError(translate("backup.need_yes", locale))
        print(translate("backup.stop_server", locale))
        answer = input(
            translate(
                "backup.confirm",
                locale,
                archive=archive,
                data_dir=paths.data_dir,
            )
        )
        if answer.strip().lower() not in {"y", "yes"}:
            print(translate("backup.cancelled", locale))
            return

    result = asyncio.run(service.import_from(archive, locale=locale))
    print(translate("backup.import_done", locale, path=paths.data_dir))
    print(f"files: {result.imported_files}")
    if result.previous_data_dir is not None:
        print(translate("backup.previous_dir", locale, path=result.previous_data_dir))


def main(argv: list[str] | None = None) -> None:
    """Start MoriBot or run a data maintenance command."""
    load_dotenv()
    args = _build_parser().parse_args(argv)
    paths = AppPaths.resolve(args.data_dir)

    if args.command == "backup":
        try:
            _run_backup_command(args, paths)
        except MoriError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            raise SystemExit(1) from exc
        return

    paths.ensure()

    config = ConfigManager(paths.config_file)
    config.load()

    log_broker = LogBroker()
    log_level = args.log_level or os.environ.get("MORIBOT_LOG_LEVEL") or config.log_level
    setup_logging(paths, log_level, log_broker)

    if args.reset_password:
        asyncio.run(_reset_password(paths, config.locale))

    from moribot.dashboard.app import create_app

    app = create_app(paths=paths, config=config, log_broker=log_broker)

    host = (
        args.host or os.environ.get("MORIBOT_HOST") or str(config.get("dashboard.host", "0.0.0.0"))
    )
    port = (
        args.port
        or int(os.environ.get("MORIBOT_PORT", "0") or 0)
        or int(config.get("dashboard.port", 6186))
    )
    ssl_certfile = (
        args.ssl_certfile or str(config.get("dashboard.ssl_certfile", "")).strip() or None
    )
    ssl_keyfile = args.ssl_keyfile or str(config.get("dashboard.ssl_keyfile", "")).strip() or None
    if bool(ssl_certfile) != bool(ssl_keyfile):
        logger.error("Both --ssl-certfile and --ssl-keyfile are required for direct HTTPS.")
        sys.exit(2)
    proxy_headers = not args.no_proxy_headers and bool(config.get("dashboard.proxy_headers", True))
    forwarded_allow_ips = (
        args.forwarded_allow_ips
        or os.environ.get("MORIBOT_FORWARDED_ALLOW_IPS")
        or str(config.get("dashboard.forwarded_allow_ips", "127.0.0.1"))
    )

    logger.info(BANNER)
    logger.info("MoriBot v{}", __version__)
    scheme = "https" if ssl_certfile and ssl_keyfile else "http"
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    logger.info("Dashboard: {}://{}:{}", scheme, display_host, port)
    logger.info("API docs:  {}://127.0.0.1:{}/api/docs", scheme, port)
    if host not in {"127.0.0.1", "localhost", "::1"} and scheme != "https":
        logger.warning(
            "MoriBot is listening on {} without direct TLS. "
            "Put it behind an HTTPS reverse proxy or tunnel, and set "
            "dashboard.public_url / force_https / trusted_hosts.",
            host,
        )
    public_url = str(config.get("dashboard.public_url", "")).strip()
    if public_url:
        logger.info("Public URL: {}", public_url)

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_config=None,
            access_log=False,
            server_header=False,
            proxy_headers=proxy_headers,
            forwarded_allow_ips=forwarded_allow_ips,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
