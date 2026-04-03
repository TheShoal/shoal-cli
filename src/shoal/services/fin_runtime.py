"""Runtime adapter for fin contract-v1 manifests and entrypoints."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from shoal.core.config import fins_dir
from shoal.models.fin import FinManifest, FinSource
from shoal.services.fin_repo import resolve_fin as _resolve_fin

logger = logging.getLogger(__name__)

# Contract versions this runtime supports. Fins declaring any other version
# are rejected at load time. Currently v1-only; extend to {1, 2} when a v2
# contract spec ships and the N/N-1 support window policy is adopted.
SUPPORTED_CONTRACT_VERSIONS: frozenset[int] = frozenset({1})


class FinRuntimeError(Exception):
    """Raised for fin manifest/runtime failures with user-facing context."""


@dataclass(frozen=True)
class FinExecutionResult:
    """Result payload from fin entrypoint execution."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class FinListItem:
    """Single fin discovery record from ``shoal fin ls``."""

    root: str
    status: str
    name: str | None = None
    version: str | None = None
    capability: str | None = None
    fin_contract_version: int | None = None
    error: str | None = None


def resolve_fin_root(fin_path: str | Path) -> Path:
    """Resolve fin root from a directory path or a manifest path."""
    candidate = Path(fin_path).expanduser().resolve()
    if candidate.is_file():
        if candidate.name != "fin.toml":
            raise FinRuntimeError(f"Expected fin.toml file, got: {candidate}")
        return candidate.parent
    if candidate.is_dir():
        return candidate
    raise FinRuntimeError(f"Fin path does not exist: {candidate}")


def load_fin_manifest(fin_path: str | Path) -> tuple[Path, FinManifest]:
    """Load and validate ``fin.toml`` for a fin root."""
    fin_root = resolve_fin_root(fin_path)
    manifest_path = fin_root / "fin.toml"
    if not manifest_path.exists():
        raise FinRuntimeError(f"Missing manifest: {manifest_path}")

    try:
        with open(manifest_path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise FinRuntimeError(f"Malformed manifest {manifest_path}: {exc}") from exc

    try:
        manifest = FinManifest.model_validate(raw)
    except ValidationError as exc:
        raise FinRuntimeError(f"Invalid manifest {manifest_path}: {exc}") from exc

    if manifest.fin_contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise FinRuntimeError(
            f"Unsupported fin_contract_version={manifest.fin_contract_version}"
            f" (supported: {sorted(SUPPORTED_CONTRACT_VERSIONS)})"
        )

    return fin_root, manifest


def resolve_entrypoint(fin_root: Path, relative_path: str) -> Path:
    """Resolve and validate an entrypoint path inside a fin root."""
    resolved = (fin_root / relative_path).resolve()
    try:
        resolved.relative_to(fin_root)
    except ValueError as exc:
        raise FinRuntimeError(f"Entrypoint escapes fin root: {relative_path}") from exc

    if not resolved.exists():
        raise FinRuntimeError(f"Entrypoint not found: {resolved}")
    if not resolved.is_file():
        raise FinRuntimeError(f"Entrypoint is not a file: {resolved}")
    if not os.access(resolved, os.X_OK):
        raise FinRuntimeError(f"Entrypoint is not executable: {resolved}")
    return resolved


def resolved_entrypoints(fin_root: Path, manifest: FinManifest) -> dict[str, Path]:
    """Return validated absolute entrypoint paths."""
    return {
        "install": resolve_entrypoint(fin_root, manifest.entrypoints.install),
        "configure": resolve_entrypoint(fin_root, manifest.entrypoints.configure),
        "run": resolve_entrypoint(fin_root, manifest.entrypoints.run),
        "validate": resolve_entrypoint(fin_root, manifest.entrypoints.validate_entrypoint),
    }


def _build_env(
    *,
    fin_root: Path,
    config_path: str | None,
    output_format: str,
) -> dict[str, str]:
    env = dict(os.environ)
    env["SHOAL_FIN_ROOT"] = str(fin_root)
    # Expose the running Python interpreter so fin scripts can use the same
    # environment that shoal itself runs in (e.g. the active virtualenv).
    env["SHOAL_PYTHON"] = sys.executable
    if config_path:
        env["SHOAL_FIN_CONFIG"] = str(Path(config_path).expanduser().resolve())
    else:
        env.pop("SHOAL_FIN_CONFIG", None)
    env["SHOAL_OUTPUT_FORMAT"] = output_format
    if not env.get("SHOAL_LOG_LEVEL"):
        # Use getEffectiveLevel() — walks the logger hierarchy so root-inherited
        # levels (e.g. WARNING from the default root logger) are captured correctly.
        level_num = logging.getLogger("shoal").getEffectiveLevel()
        if level_num != logging.NOTSET:
            env["SHOAL_LOG_LEVEL"] = logging.getLevelName(level_num)
    return env


def execute_entrypoint(
    *,
    fin_root: Path,
    entrypoint: Path,
    args: list[str],
    config_path: str | None,
    output_format: str,
    timeout: int | None = None,
) -> FinExecutionResult:
    """Execute a fin lifecycle entrypoint as subprocess.

    Args:
        fin_root: Absolute path to the fin root directory.
        entrypoint: Resolved, executable entrypoint path.
        args: Arguments forwarded verbatim to the entrypoint.
        config_path: Optional path written to ``SHOAL_FIN_CONFIG`` env var.
        output_format: Value written to ``SHOAL_OUTPUT_FORMAT`` env var.
        timeout: Maximum wall-clock seconds allowed.  ``None`` means no limit.
            On expiry the process is killed and ``FinRuntimeError`` is raised.
    """
    cmd = [str(entrypoint), *args]
    env = _build_env(fin_root=fin_root, config_path=config_path, output_format=output_format)
    try:
        result = subprocess.run(
            cmd,
            cwd=fin_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise FinRuntimeError(f"Fin entrypoint timed out after {timeout}s: {entrypoint}") from None
    except OSError as exc:
        raise FinRuntimeError(f"Failed to execute {entrypoint}: {exc}") from exc

    return FinExecutionResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def inspect_fin(fin_path: str | Path) -> dict[str, object]:
    """Load a fin and return metadata with resolved entrypoints."""
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoints = resolved_entrypoints(fin_root, manifest)
    return {
        "root": str(fin_root),
        "name": manifest.name,
        "version": manifest.version,
        "fin_contract_version": manifest.fin_contract_version,
        "capability": manifest.capability,
        "entrypoints": {k: str(v) for k, v in entrypoints.items()},
    }


def validate_fin(
    fin_path: str | Path,
    *,
    strict: bool,
    timeout: int | None = None,
) -> FinExecutionResult:
    """Execute a fin's ``validate`` entrypoint after manifest checks.

    Args:
        fin_path: Path to fin root directory or fin.toml file.
        strict: Forward ``--strict`` flag to the entrypoint.
        timeout: Override seconds limit.  Falls back to
            ``manifest.default_timeout_seconds``, then no limit.
    """
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.validate_entrypoint)
    resolved_timeout = timeout if timeout is not None else manifest.default_timeout_seconds
    args = ["--strict"] if strict else []
    return execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=args,
        config_path=None,
        output_format="text",
        timeout=resolved_timeout,
    )


def install_fin(
    fin_path: str | Path,
    *,
    register: bool = True,
    timeout: int | None = None,
    registry_url: str = "https://fins.shoal.dev",
) -> FinExecutionResult:
    """Execute a fin's ``install`` entrypoint after manifest checks.

    Args:
        fin_path: Path to fin root directory or fin.toml file.  Also accepts
            ``http(s)://`` URLs and ``fin:<name>[@<version>]`` shorthands.
        register: If True (default), copy the fin into ``fins_dir()`` after
            a successful entrypoint run.  Registration failures emit a warning
            but do not affect the returned result.
        timeout: Override seconds limit.  Falls back to
            ``manifest.default_timeout_seconds``, then no limit.
        registry_url: Base URL used to resolve ``fin:`` shorthand sources.

    Returns:
        Result of the install entrypoint execution.
    """

    source = FinSource.parse(str(fin_path))
    if source.kind != "local":
        try:
            fin_path = _resolve_fin(source, registry_url)
        except ValueError as exc:
            raise FinRuntimeError(str(exc)) from exc
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.install)
    resolved_timeout = timeout if timeout is not None else manifest.default_timeout_seconds
    result = execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=[],
        config_path=None,
        output_format="text",
        timeout=resolved_timeout,
    )
    if register:
        try:
            register_fin(fin_path)
        except FinRuntimeError as exc:
            logger.warning("Failed to register fin '%s': %s", manifest.name, exc)
    return result


def register_fin(fin_path: str | Path, *, force: bool = True) -> Path:
    """Copy a fin into the local registry (``fins_dir()``).

    Args:
        fin_path: Path to fin root directory or fin.toml file.
        force: If True (default), overwrite any existing registration.

    Returns:
        The destination path under ``fins_dir()``.

    Raises:
        FinRuntimeError: If the source path does not exist.
    """
    fin_root, manifest = load_fin_manifest(fin_path)
    dest = fins_dir() / manifest.name

    src = Path(fin_path).expanduser().resolve()
    if src.is_file():
        # fin_path points to fin.toml; register the parent directory
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fin_root / "fin.toml", dest / "fin.toml")
    elif src.is_dir():
        shutil.copytree(fin_root, dest, dirs_exist_ok=force)
    else:
        raise FinRuntimeError(f"Fin path does not exist: {src}")

    return dest


def list_registered_fins() -> list[FinListItem]:
    """List fins registered in ``fins_dir()``.

    Walks immediate subdirectories of ``fins_dir()`` for valid fin.toml files.
    Returns an empty list if the registry directory does not exist.

    Returns:
        List of fin discovery records, one per registered fin.
    """
    registry = fins_dir()
    if not registry.exists():
        return []

    items: list[FinListItem] = []
    for child in sorted(registry.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "fin.toml"
        if not manifest_path.exists():
            continue
        try:
            _, manifest = load_fin_manifest(manifest_path)
            items.append(
                FinListItem(
                    root=str(child),
                    status="valid",
                    name=manifest.name,
                    version=manifest.version,
                    capability=manifest.capability,
                    fin_contract_version=manifest.fin_contract_version,
                )
            )
        except FinRuntimeError as exc:
            items.append(
                FinListItem(
                    root=str(child),
                    status="invalid",
                    error=str(exc),
                )
            )

    return items


def configure_fin(
    fin_path: str | Path,
    *,
    config_path: str | None,
    timeout: int | None = None,
) -> FinExecutionResult:
    """Execute a fin's ``configure`` entrypoint after manifest checks.

    Args:
        fin_path: Path to fin root directory or fin.toml file.
        config_path: Optional path forwarded as ``SHOAL_FIN_CONFIG``.
        timeout: Override seconds limit.  Falls back to
            ``manifest.default_timeout_seconds``, then no limit.
    """
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.configure)
    resolved_timeout = timeout if timeout is not None else manifest.default_timeout_seconds
    return execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=[],
        config_path=config_path,
        output_format="text",
        timeout=resolved_timeout,
    )


def run_fin(
    fin_path: str | Path,
    *,
    config_path: str | None,
    output_format: str,
    args: list[str],
    timeout: int | None = None,
) -> FinExecutionResult:
    """Execute a fin's ``run`` entrypoint with passthrough args.

    Args:
        fin_path: Path to fin root directory or fin.toml file.
        config_path: Optional path forwarded as ``SHOAL_FIN_CONFIG``.
        output_format: ``text`` or ``json``.
        args: Arguments forwarded verbatim after ``--``.
        timeout: Override seconds limit.  Falls back to
            ``manifest.default_timeout_seconds``, then no limit.
    """
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.run)
    resolved_timeout = timeout if timeout is not None else manifest.default_timeout_seconds
    return execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=args,
        config_path=config_path,
        output_format=output_format,
        timeout=resolved_timeout,
    )


def list_fins(search_path: str | Path) -> list[FinListItem]:
    """List path-based fin candidates from a directory or ``fin.toml`` path."""
    root = Path(search_path).expanduser().resolve()
    candidates: list[Path] = []

    if root.is_file():
        if root.name != "fin.toml":
            raise FinRuntimeError(f"Expected fin.toml file, got: {root}")
        candidates = [root]
    elif root.is_dir():
        direct_manifest = root / "fin.toml"
        if direct_manifest.exists():
            candidates.append(direct_manifest)
        for child in sorted(root.iterdir()):
            child_manifest = child / "fin.toml"
            if child.is_dir() and child_manifest.exists():
                candidates.append(child_manifest)
    else:
        raise FinRuntimeError(f"Fin discovery path does not exist: {root}")

    items: list[FinListItem] = []
    for manifest_path in candidates:
        fin_root = manifest_path.parent
        try:
            _, manifest = load_fin_manifest(manifest_path)
            items.append(
                FinListItem(
                    root=str(fin_root),
                    status="valid",
                    name=manifest.name,
                    version=manifest.version,
                    capability=manifest.capability,
                    fin_contract_version=manifest.fin_contract_version,
                )
            )
        except FinRuntimeError as exc:
            items.append(
                FinListItem(
                    root=str(fin_root),
                    status="invalid",
                    error=str(exc),
                )
            )

    return items
