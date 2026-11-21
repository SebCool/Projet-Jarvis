"""Wrapper ADB minimal. Toute interaction avec le téléphone passe par ici."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass


class AdbError(RuntimeError):
    pass


@dataclass
class AdbResult:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class Adb:
    """Appelle le binaire `adb`. `serial` = "IP:port" (Wireless debugging) ou n° USB."""

    def __init__(self, adb_path: str | None = None, serial: str | None = None, timeout: int = 30):
        self.adb_path = adb_path or os.environ.get("ANDROID_PILOT_ADB") or shutil.which("adb") or "adb"
        self.serial = serial or os.environ.get("ANDROID_PILOT_SERIAL") or None
        self.timeout = timeout

    # --- bas niveau -------------------------------------------------------
    def _base(self) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, *args: str, timeout: int | None = None, binary: bool = False) -> AdbResult:
        try:
            p = subprocess.run(
                self._base() + list(args),
                capture_output=True,
                timeout=timeout or self.timeout,
            )
        except FileNotFoundError as e:
            raise AdbError(f"adb introuvable ({self.adb_path}). Installer platform-tools ou définir ANDROID_PILOT_ADB.") from e
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"Timeout adb {' '.join(args)}") from e
        if binary:
            return AdbResult(p.returncode, p.stdout, p.stderr.decode(errors="replace"))  # type: ignore[arg-type]
        return AdbResult(
            p.returncode,
            p.stdout.decode(errors="replace").strip(),
            p.stderr.decode(errors="replace").strip(),
        )

    def shell(self, *argv: str, check: bool = True, timeout: int | None = None) -> str:
        """Exécute une commande sur le téléphone. Les arguments sont quotés individuellement."""
        cmd = " ".join(shlex.quote(a) for a in argv)
        r = self.run("shell", cmd, timeout=timeout)
        if check and not r.ok:
            raise AdbError(f"`{cmd}` → code {r.code}: {r.err or r.out}")
        return r.out

    def shell_raw(self, cmd: str, timeout: int | None = None) -> AdbResult:
        """Commande shell brute (pipes, redirections). Réservé aux outils explicitement non sûrs."""
        return self.run("shell", cmd, timeout=timeout)

    def exec_out(self, *argv: str) -> bytes:
        r = self.run("exec-out", *argv, binary=True)
        if not r.ok:
            raise AdbError(f"exec-out {' '.join(argv)} → {r.err}")
        return r.out  # type: ignore[return-value]

    # --- connexion --------------------------------------------------------
    def devices(self) -> str:
        return self.run("devices", "-l").out

    def connect(self, host_port: str) -> str:
        r = Adb(self.adb_path).run("connect", host_port)
        if "connected" in r.out and "cannot" not in r.out:
            self.serial = host_port
        return r.out or r.err

    def pair(self, host_port: str, code: str) -> str:
        r = Adb(self.adb_path).run("pair", host_port, code)
        return r.out or r.err

    # --- helpers ----------------------------------------------------------
    def getprop(self, key: str) -> str:
        return self.shell("getprop", key, check=False)

    def settings_get(self, namespace: str, key: str) -> str | None:
        v = self.shell("settings", "get", namespace, key, check=False)
        return None if v in ("null", "") else v

    def settings_put(self, namespace: str, key: str, value: str | None) -> None:
        if value is None:
            self.shell("settings", "delete", namespace, key)
        else:
            self.shell("settings", "put", namespace, key, value)

    def package_state(self, package: str) -> str:
        """Retourne 'enabled', 'disabled', 'uninstalled' (pour user 0) ou 'absent'."""
        if package not in self._list("-u"):
            return "absent"
        if package not in self._list():
            return "uninstalled"
        if package in self._list("-d"):
            return "disabled"
        return "enabled"

    def _list(self, *flags: str) -> set[str]:
        out = self.shell("pm", "list", "packages", *flags, "--user", "0", check=False)
        return {line.removeprefix("package:").strip() for line in out.splitlines() if line.startswith("package:")}
