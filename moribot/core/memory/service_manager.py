"""MoriBot host-side lifecycle manager for the embedded MoriMemory service.

This module is intentionally free of MoriBot imports so it can be copied into
``moribot/core/memory/service.py`` without pulling in the memory engine. It
starts the service on demand, reuses an already healthy instance, and never
spawns a second process for the same data directory/port.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


@dataclass(slots=True)
class MemoryServiceSettings:
    enabled: bool = True
    auto_start: bool = True
    auto_restart: bool = True
    home: Path | None = None
    data_dir: Path | None = None
    port: int = 6190
    host: str = "127.0.0.1"
    token: str = ""
    startup_timeout_seconds: float = 30.0
    request_timeout_seconds: float = 120.0

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(slots=True)
class MemoryServiceStatus:
    running: bool
    owned: bool
    base_url: str
    pid: int | None = None
    version: str = ""
    database_ok: bool = False
    fts5: bool = False
    error: str = ""


class MemoryServiceManager:
    def __init__(self, settings: MemoryServiceSettings) -> None:
        self.settings = settings
        self._process: subprocess.Popen | None = None
        self._owned = False
        self._monitor: asyncio.Task | None = None
        self._stopping = False
        self._log_handle = None
        self._last_error = ""
        self._guard = asyncio.Lock()

    @classmethod
    def from_host(
        cls,
        *,
        project_root: Path,
        data_dir: Path,
        config: dict[str, Any],
    ) -> MemoryServiceManager:
        """Build settings from a MoriBot-style config section."""

        home_value = str(config.get("home") or "").strip()
        home = Path(home_value).expanduser() if home_value else None
        if home is None or not home.exists():
            env_home = os.environ.get("MORIMEMORY_HOME", "").strip()
            if env_home:
                home = Path(env_home).expanduser()
            else:
                candidate = project_root.parent / "MoriMemory"
                home = candidate if candidate.exists() else None
        return cls(
            MemoryServiceSettings(
                enabled=bool(config.get("enabled", True)),
                auto_start=bool(config.get("auto_start", True)),
                auto_restart=bool(config.get("auto_restart", True)),
                home=home,
                data_dir=data_dir / "memory",
                port=int(config.get("port", 6190) or 6190),
                host=str(config.get("host", "127.0.0.1") or "127.0.0.1"),
                token=str(config.get("service_token", "") or ""),
                startup_timeout_seconds=float(config.get("startup_timeout_seconds", 30) or 30),
                request_timeout_seconds=float(config.get("request_timeout_seconds", 120) or 120),
            )
        )

    @property
    def base_url(self) -> str:
        return self.settings.base_url

    @property
    def token(self) -> str:
        self._ensure_token()
        return self.settings.token

    @property
    def data_dir(self) -> Path:
        return self.settings.data_dir or Path.cwd() / "data" / "memory"

    @property
    def _lock_file(self) -> Path:
        return self.data_dir / "memory-service.lock"

    @property
    def _token_file(self) -> Path:
        return self.data_dir / "service-token"

    def _ensure_token(self) -> None:
        if self.settings.token:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self._token_file.is_file():
                token = self._token_file.read_text(encoding="utf-8").strip()
            else:
                token = secrets.token_urlsafe(48)
                self._token_file.write_text(token + "\n", encoding="utf-8")
                with contextlib.suppress(OSError):
                    os.chmod(self._token_file, 0o600)
            self.settings.token = token
        except OSError:
            logger.exception("Could not read or create the MoriMemory service token.")
            self.settings.token = secrets.token_urlsafe(48)

    async def ensure_started(self) -> bool:
        """Reuse a healthy instance or start the service process."""

        async with self._guard:
            return await self._ensure_started_locked()

    async def _ensure_started_locked(self) -> bool:
        if not self.settings.enabled:
            return False
        self._ensure_token()
        health = await self.health()
        if health is not None:
            self._last_error = ""
            return True
        if not self.settings.auto_start:
            self._last_error = "MoriMemory is not running and auto_start is disabled."
            return False

        lock = self._read_lock()
        if lock and self._pid_alive(int(lock.get("pid", 0))):
            if await self._wait_for_health(self.settings.startup_timeout_seconds):
                return True
            logger.warning(
                "MoriMemory lock points at live PID {} but health is unavailable; "
                "reusing the process instead of spawning another.",
                lock.get("pid"),
            )
            self._last_error = "MoriMemory process is alive but not ready."
            return False

        self._write_lock()
        return await self._spawn()

    async def _spawn(self) -> bool:
        if not self._find_home():
            self._last_error = (
                "MoriMemory source checkout not found. Set MORIMEMORY_HOME "
                "or memory.home to the MoriMemory repository."
            )
            logger.warning(self._last_error)
            self._remove_lock()
            return False

        self._stopping = False
        command = self._build_command()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.data_dir / "memory-service.out.log"
        self._log_handle = log_path.open("ab")
        env = os.environ.copy()
        env["MORIMEMORY_TOKEN"] = self.settings.token
        env["MORIMEMORY_DATA_DIR"] = str(self.data_dir)
        env["MORIMEMORY_HOST"] = self.settings.host
        env["MORIMEMORY_PORT"] = str(self.settings.port)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(  # noqa: S603, ASYNC220 - local controlled command
                command,
                cwd=str(self.settings.home),
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self._owned = True
            self._write_lock()
            logger.info(
                "Starting embedded MoriMemory at {} (pid={}).",
                self.settings.base_url,
                self._process.pid,
            )
            if await self._wait_for_health(self.settings.startup_timeout_seconds):
                if self.settings.auto_restart and (self._monitor is None or self._monitor.done()):
                    self._monitor = asyncio.create_task(self._watch(), name="memory-service-watch")
                self._last_error = ""
                return True
            self._last_error = (
                f"MoriMemory did not become healthy within "
                f"{self.settings.startup_timeout_seconds:.0f}s. See {log_path}."
            )
            logger.error(self._last_error)
            await self.stop(kill_owned=True)
            return False
        except OSError as exc:
            self._last_error = f"Could not start MoriMemory: {exc}"
            logger.exception(self._last_error)
            self._remove_lock()
            return False

    def _build_command(self) -> list[str]:
        assert self.settings.home is not None
        args = [
            "serve",
            "--data-dir",
            str(self.data_dir),
            "--host",
            self.settings.host,
            "--port",
            str(self.settings.port),
        ]
        if sys.platform == "win32":
            venv_python = self.settings.home / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = self.settings.home / ".venv" / "bin" / "python"
        if venv_python.is_file():
            return [str(venv_python), "-m", "morimemory", *args]
        uv = shutil.which("uv")
        if uv:
            return [uv, "run", "--project", str(self.settings.home), "morimemory", *args]
        return [sys.executable, "-m", "morimemory", *args]

    async def _wait_for_health(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if await self.health() is not None:
                return True
            if self._process is not None and self._process.poll() is not None:
                return False
            await asyncio.sleep(0.4)
        return False

    async def health(self) -> dict[str, Any] | None:
        try:
            # The embedded service is always a loopback target. Ignore any
            # HTTP_PROXY/ALL_PROXY inherited from the desktop environment.
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
            if response.status_code != 200:
                return None
            payload = response.json()
            if payload.get("service") != "morimemory":
                return None
            return payload
        except (httpx.HTTPError, ValueError):
            return None

    async def status(self) -> MemoryServiceStatus:
        health = await self.health()
        lock = self._read_lock()
        return MemoryServiceStatus(
            running=health is not None,
            owned=self._owned,
            base_url=self.base_url,
            pid=int(lock.get("pid", 0)) if lock else None,
            version=str(health.get("version", "")) if health else "",
            database_ok=bool(health.get("database", {}).get("ok")) if health else False,
            fts5=bool(health.get("database", {}).get("fts5")) if health else False,
            error=self._last_error,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        self._ensure_token()
        request_headers = {
            "Authorization": f"Bearer {self.settings.token}",
            "X-Mori-Role": "admin",
            **(headers or {}),
        }
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            trust_env=False,
        ) as client:
            return await client.request(
                method,
                f"{self.base_url}/api/v1/{path.lstrip('/')}",
                params=params,
                headers=request_headers,
                content=content,
            )

    async def _watch(self) -> None:
        while not self._stopping:
            await asyncio.sleep(5)
            if self._stopping:
                return
            if self._process is not None and self._process.poll() is not None:
                logger.warning(
                    "Embedded MoriMemory exited unexpectedly (code={}); restarting.",
                    self._process.returncode,
                )
                self._owned = False
                self._process = None
                self._remove_lock()
                await self.ensure_started()

    async def stop(self, *, kill_owned: bool = True) -> None:
        self._stopping = True
        if self._monitor is not None:
            self._monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor
            self._monitor = None
        process = self._process
        self._process = None
        if process is not None and kill_owned and self._owned and process.poll() is None:
            logger.info("Stopping embedded MoriMemory (pid={}).", process.pid)
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)
        self._owned = False
        self._remove_lock()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _find_home(self) -> bool:
        if not self.settings.home:
            return False
        home = self.settings.home
        return (home / "morimemory" / "cli.py").is_file() or (home / "pyproject.toml").is_file()

    def _read_lock(self) -> dict[str, Any] | None:
        try:
            if not self._lock_file.is_file():
                return None
            data = json.loads(self._lock_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            locked_dir = str(data.get("data_dir") or "").strip()
            if locked_dir:
                try:
                    if Path(locked_dir).resolve() != self.data_dir.resolve():
                        return None
                except OSError:
                    return None
            try:
                locked_port = int(data.get("port", self.settings.port))
            except (TypeError, ValueError):
                locked_port = self.settings.port
            if locked_port != self.settings.port:
                return None
            return data
        except (OSError, ValueError):
            return None

    def _write_lock(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": self._process.pid if self._process else os.getpid(),
            "port": self.settings.port,
            "data_dir": str(self.data_dir),
            "updated_at": time.time(),
        }
        temp = self._lock_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp, self._lock_file)

    def _remove_lock(self) -> None:
        with contextlib.suppress(OSError):
            self._lock_file.unlink(missing_ok=True)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
            if not process:
                return False
            ctypes.windll.kernel32.CloseHandle(process)  # type: ignore[attr-defined]
            return True
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
