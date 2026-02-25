"""Runtime adapter for fin contract-v1 manifests and entrypoints."""

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from shoal.models.fin import FinManifest


class FinRuntimeError(Exception):
    """Raised for fin manifest/runtime failures with user-facing context."""


@dataclass(frozen=True)
class FinExecutionResult:
    """Result payload from fin entrypoint execution."""

    exit_code: int
    stdout: str
    stderr: str


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

    if manifest.fin_contract_version != 1:
        raise FinRuntimeError(
            f"Unsupported fin_contract_version={manifest.fin_contract_version} (expected 1)"
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
    if config_path:
        env["SHOAL_FIN_CONFIG"] = str(Path(config_path).expanduser().resolve())
    else:
        env.pop("SHOAL_FIN_CONFIG", None)
    env["SHOAL_OUTPUT_FORMAT"] = output_format
    return env


def execute_entrypoint(
    *,
    fin_root: Path,
    entrypoint: Path,
    args: list[str],
    config_path: str | None,
    output_format: str,
) -> FinExecutionResult:
    """Execute a fin lifecycle entrypoint as subprocess."""
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
        )
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


def validate_fin(fin_path: str | Path, *, strict: bool) -> FinExecutionResult:
    """Execute a fin's ``validate`` entrypoint after manifest checks."""
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.validate_entrypoint)
    args = ["--strict"] if strict else []
    return execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=args,
        config_path=None,
        output_format="text",
    )


def run_fin(
    fin_path: str | Path,
    *,
    config_path: str | None,
    output_format: str,
    args: list[str],
) -> FinExecutionResult:
    """Execute a fin's ``run`` entrypoint with passthrough args."""
    fin_root, manifest = load_fin_manifest(fin_path)
    entrypoint = resolve_entrypoint(fin_root, manifest.entrypoints.run)
    return execute_entrypoint(
        fin_root=fin_root,
        entrypoint=entrypoint,
        args=args,
        config_path=config_path,
        output_format=output_format,
    )
