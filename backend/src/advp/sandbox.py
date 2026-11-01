"""Restricted Python subprocess for generated-code validation.

This is a local restricted subprocess, not a container. It blocks network,
subprocess, and out-of-workspace writes through an audit hook and enforces a
wall-clock timeout.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field

from advp.config import get_settings
from advp.eu2_settings import runtime_setting

BOOTSTRAP = r"""
import os
import runpy
import sys

WORKDIR = os.path.realpath(os.getcwd())
BLOCKED = {
    "socket.connect",
    "socket.bind",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "ctypes.dlopen",
    "ctypes.dlsym",
    "winreg.OpenKey",
    "winreg.CreateKey",
}
BLOCKED_IMPORTS = {
    "socket",
    "subprocess",
    "ctypes",
    "urllib",
    "http",
    "requests",
    "httpx",
    "ftplib",
    "smtplib",
    "telnetlib",
    "winreg",
    "multiprocessing",
    "pty",
    "asyncio",
}
ALLOWED_THIRD_PARTY = {
    "numpy",
    "pandas",
    "plotly",
    "networkx",
    "matplotlib",
    "nibabel",
    "pydicom",
    "h5py",
    "xarray",
    "astropy",
    "dateutil",
    "pytz",
    "tzdata",
    "six",
    "packaging",
    "pyparsing",
    "kiwisolver",
    "cycler",
    "fontTools",
    "PIL",
    "scipy",
    "defusedxml",
    "tenacity",
    "narwhals",
    "yaml",
    "lark",
    "attrs",
    "platformdirs",
    "typing_extensions",
    "pyerfa",
    "contourpy",
}
WRITE_EVENTS = {"os.remove", "os.rename", "os.mkdir", "os.rmdir"}

def _safe(value):
    try:
        text = os.fsdecode(value)
    except (TypeError, ValueError):
        return True
    path = os.path.realpath(text)
    return path == WORKDIR or path.startswith(WORKDIR + os.sep)

def _hook(event, args):
    if event in BLOCKED:
        raise PermissionError("sandbox blocked " + event)
    if event == "import" and args:
        root = str(args[0]).split(".")[0]
        if root in BLOCKED_IMPORTS:
            raise PermissionError("sandbox blocked import " + root)
        if root not in sys.stdlib_module_names and root not in ALLOWED_THIRD_PARTY:
            raise PermissionError("sandbox import is not allowlisted: " + root)
    if event == "open" and args:
        mode = str(args[1] or "")
        path = args[0]
        if any(flag in mode for flag in ("w", "a", "x", "+")) and not _safe(path):
            raise PermissionError("sandbox blocked write outside workdir")
    if event in WRITE_EVENTS and args and not _safe(args[0]):
        raise PermissionError("sandbox blocked filesystem change outside workdir")

sys.addaudithook(_hook)
script = sys.argv[1]
sys.argv = [script]
runpy.run_path(script, run_name="__main__")
"""


@dataclass(slots=True)
class SandboxResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    error: str | None = None
    workdir: str = field(default="")

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


def run_python(
    code: str,
    *,
    timeout: float | None = None,
    max_output: int = 20_000,
) -> SandboxResult:
    """Run Python code in a restricted child process."""
    settings = get_settings()
    if timeout is None:
        timeout = float(runtime_setting(settings, "sandbox_timeout_seconds"))
    workdir = settings.workspace_dir / "sandbox" / uuid.uuid4().hex
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "main.py"
    runner = workdir / "_runner.py"
    script.write_text(code, encoding="utf-8")
    runner.write_text(BOOTSTRAP, encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "TEMP": str(workdir),
        "TMP": str(workdir),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
    }
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", str(runner), str(script)],
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job = _apply_windows_limits(process, timeout)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            duration = int((time.monotonic() - started) * 1000)
            return SandboxResult(
                ok=False,
                exit_code=None,
                stdout=_text(stdout)[-max_output:],
                stderr=_text(stderr)[-max_output:],
                duration_ms=duration,
                error=f"sandbox timeout after {timeout:g}s",
            )
        finally:
            if job is not None:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(job)
        duration = int((time.monotonic() - started) * 1000)
        stdout = _text(stdout)[-max_output:]
        stderr = _text(stderr)[-max_output:]
        return SandboxResult(
            ok=process.returncode == 0,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration,
            error=None if process.returncode == 0 else stderr.strip() or "non-zero exit",
        )
    except OSError as exc:
        duration = int((time.monotonic() - started) * 1000)
        return SandboxResult(
            ok=False,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            duration_ms=duration,
            error=str(exc),
        )
    finally:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)


def _apply_windows_limits(process: subprocess.Popen[str], timeout: float) -> int | None:
    """Best-effort Job Object time/memory limits on Windows."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2 | 0x100 | 0x2000
        info.BasicLimitInformation.PerProcessUserTimeLimit = int(timeout * 10_000_000)
        info.ProcessMemoryLimit = 1024 * 1024 * 1024
        if not kernel32.SetInformationJobObject(
            job,
            9,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(job)
            return None
        handle = int(process._handle)  # type: ignore[attr-defined]
        if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(handle)):
            kernel32.CloseHandle(job)
            return None
        return int(job)
    except Exception:
        return None


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
