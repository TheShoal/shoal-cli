"""SSH tunnel management and remote API client for Shoal."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from shoal.core.config import data_dir, load_config

logger = logging.getLogger(__name__)


def _redact_ssh_cmd(cmd: list[str]) -> str:
    """Redact sensitive arguments from an SSH command for logging.

    Replaces the argument after ``-i`` (identity file path) with ``<redacted>``.
    """
    parts: list[str] = []
    redact_next = False
    for arg in cmd:
        if redact_next:
            parts.append("<redacted>")
            redact_next = False
        elif arg == "-i":
            parts.append(arg)
            redact_next = True
        else:
            parts.append(arg)
    return " ".join(parts)


class RemoteConnectionError(Exception):
    """SSH tunnel or HTTP connection to remote host failed."""

    def __init__(self, message: str, *, host: str = "") -> None:
        self.host = host
        super().__init__(message)


# --- Tunnel state file helpers ---


def _remote_dir() -> Path:
    """Return the remote tunnel state directory."""
    return data_dir() / "remote"


def tunnel_pid_file(host: str) -> Path:
    """Return PID file path for a tunnel."""
    return _remote_dir() / f"{host}.pid"


def tunnel_port_file(host: str) -> Path:
    """Return port file path for a tunnel."""
    return _remote_dir() / f"{host}.port"


def read_tunnel_pid(host: str) -> int | None:
    """Read the SSH tunnel PID, or None if not found."""
    pf = tunnel_pid_file(host)
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except (ValueError, OSError):
        return None


def read_tunnel_port(host: str) -> int | None:
    """Read the local forwarded port, or None if not found."""
    pf = tunnel_port_file(host)
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_tunnel_active(host: str) -> bool:
    """Check if an SSH tunnel is active for the given host."""
    pid = read_tunnel_pid(host)
    if pid is None:
        return False
    if not _pid_alive(pid):
        # Stale PID file — clean up
        tunnel_pid_file(host).unlink(missing_ok=True)
        tunnel_port_file(host).unlink(missing_ok=True)
        return False
    return True


# --- Tunnel lifecycle ---


def _find_free_port() -> int:
    """Find a free local port for the SSH tunnel."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def start_tunnel(
    host: str,
    ssh_host: str,
    remote_port: int,
    *,
    local_port: int | None = None,
    user: str = "",
    identity_file: str = "",
    ssh_port: int = 22,
) -> int:
    """Start an SSH tunnel. Returns the local port.

    Raises RuntimeError if the tunnel fails to start.
    """
    if is_tunnel_active(host):
        raise RuntimeError(f"Tunnel to '{host}' is already active")

    port = local_port or _find_free_port()

    cmd: list[str] = [
        "ssh",
        "-f",
        "-N",
        "-L",
        f"{port}:localhost:{remote_port}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
    ]

    if ssh_port != 22:
        cmd.extend(["-p", str(ssh_port)])
    if identity_file:
        cmd.extend(["-i", os.path.expanduser(identity_file)])

    target = f"{user}@{ssh_host}" if user else ssh_host
    cmd.append(target)

    logger.info("Starting SSH tunnel: %s", _redact_ssh_cmd(cmd))

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"SSH tunnel to '{host}' failed: {e.stderr.strip()}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"SSH tunnel to '{host}' timed out") from e

    # ssh -f backgrounds itself — find the PID via port scan
    time.sleep(0.5)
    pid = _find_tunnel_pid(port)
    if pid is None:
        raise RuntimeError(f"SSH tunnel to '{host}' started but PID not found")

    # Write state files
    _remote_dir().mkdir(parents=True, exist_ok=True)
    tunnel_pid_file(host).write_text(str(pid))
    tunnel_port_file(host).write_text(str(port))

    logger.info("Tunnel to '%s' active: pid=%d, local_port=%d", host, pid, port)
    return port


def _find_tunnel_pid(local_port: int) -> int | None:
    """Find the PID of an SSH process listening on the given local port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"TCP:{local_port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().splitlines()[0])
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def stop_tunnel(host: str) -> bool:
    """Stop an SSH tunnel. Returns True if a tunnel was stopped."""
    pid = read_tunnel_pid(host)
    if pid is None:
        return False

    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("Stopped tunnel to '%s' (pid=%d)", host, pid)
        except ProcessLookupError:
            pass

    tunnel_pid_file(host).unlink(missing_ok=True)
    tunnel_port_file(host).unlink(missing_ok=True)
    return True


def list_tunnels() -> list[tuple[str, int, int]]:
    """List active tunnels. Returns [(host, pid, local_port), ...]."""
    remote = _remote_dir()
    if not remote.exists():
        return []

    tunnels: list[tuple[str, int, int]] = []
    for pid_file in sorted(remote.glob("*.pid")):
        host = pid_file.stem
        if is_tunnel_active(host):
            pid = read_tunnel_pid(host)
            port = read_tunnel_port(host)
            if pid is not None and port is not None:
                tunnels.append((host, pid, port))
    return tunnels


# --- HTTP client helpers ---


def _get_base_url(host: str) -> str:
    """Get the base URL for a remote host's API."""
    port = read_tunnel_port(host)
    if port is None:
        raise RemoteConnectionError(
            f"No active tunnel to '{host}'. Run: shoal remote connect {host}",
            host=host,
        )
    return f"http://localhost:{port}"


def remote_api_get(host: str, path: str) -> Any:
    """GET request to remote Shoal API. Returns parsed JSON."""
    url = f"{_get_base_url(host)}{path}"
    req = urllib.request.Request(url)  # noqa: S310 — always localhost
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError) as e:
        reason = e.reason if isinstance(e, urllib.error.URLError) else str(e)
        raise RemoteConnectionError(
            f"Failed to connect to '{host}': {reason}",
            host=host,
        ) from e
    except json.JSONDecodeError as e:
        raise RemoteConnectionError(
            f"Invalid response from '{host}': {e}",
            host=host,
        ) from e


def remote_api_post(host: str, path: str, data: dict[str, Any] | None = None) -> Any:
    """POST request to remote Shoal API. Returns parsed JSON."""
    url = f"{_get_base_url(host)}{path}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST")  # noqa: S310  # nosec B310
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError) as e:
        reason = e.reason if isinstance(e, urllib.error.URLError) else str(e)
        raise RemoteConnectionError(
            f"Failed to connect to '{host}': {reason}",
            host=host,
        ) from e
    except json.JSONDecodeError as e:
        raise RemoteConnectionError(
            f"Invalid response from '{host}': {e}",
            host=host,
        ) from e


def remote_api_delete(host: str, path: str) -> Any:
    """DELETE request to remote Shoal API. Returns parsed JSON."""
    url = f"{_get_base_url(host)}{path}"
    req = urllib.request.Request(url, method="DELETE")  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError) as e:
        reason = e.reason if isinstance(e, urllib.error.URLError) else str(e)
        raise RemoteConnectionError(
            f"Failed to connect to '{host}': {reason}",
            host=host,
        ) from e
    except json.JSONDecodeError as e:
        raise RemoteConnectionError(
            f"Invalid response from '{host}': {e}",
            host=host,
        ) from e


def resolve_host(name: str) -> dict[str, Any]:
    """Resolve a remote host name to its config. Returns config dict.

    Raises typer.Exit if the host is not configured.
    """
    cfg = load_config()
    if name not in cfg.remote:
        msg = f"Unknown remote host: '{name}'"
        available = list(cfg.remote.keys())
        if available:
            msg += f"\nConfigured hosts: {', '.join(available)}"
        else:
            msg += "\nNo remote hosts configured. Add to ~/.config/shoal/config.toml:\n"
            msg += f'\n[remote.{name}]\nhost = "{name}.example.com"\n'
        raise KeyError(msg)
    host_cfg = cfg.remote[name]
    return {
        "name": name,
        "host": host_cfg.host,
        "port": host_cfg.port,
        "user": host_cfg.user,
        "identity_file": host_cfg.identity_file,
        "api_port": host_cfg.api_port,
    }
