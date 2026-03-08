"""Tests for services/fin_runtime.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from shoal.services.fin_runtime import (
    FinExecutionResult,
    FinRuntimeError,
    configure_fin,
    install_fin,
    list_fins,
    list_registered_fins,
    load_fin_manifest,
    register_fin,
    run_fin,
    validate_fin,
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _create_fin(tmp_path: Path) -> Path:
    fin_root = tmp_path / "example-fin"
    bin_dir = fin_root / "bin"
    bin_dir.mkdir(parents=True)

    (fin_root / "fin.toml").write_text(
        """
name = "example-fin"
version = "0.1.0"
fin_contract_version = 1
capability = "example.capability"

[entrypoints]
install = "bin/install"
configure = "bin/configure"
run = "bin/run"
validate = "bin/validate"
""".strip()
        + "\n"
    )

    _write_executable(
        bin_dir / "install",
        "#!/bin/sh\necho install-ok\nexit 0\n",
    )
    _write_executable(
        bin_dir / "configure",
        '#!/bin/sh\necho "configure:$SHOAL_FIN_CONFIG"\nexit 0\n',
    )
    _write_executable(
        bin_dir / "validate",
        '#!/bin/sh\nif [ "$1" = "--strict" ]; then echo strict-ok; fi\nexit 0\n',
    )
    _write_executable(
        bin_dir / "run",
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "payload = {\n"
        '  "args": sys.argv[1:],\n'
        '  "root": os.environ.get("SHOAL_FIN_ROOT"),\n'
        '  "config": os.environ.get("SHOAL_FIN_CONFIG"),\n'
        '  "format": os.environ.get("SHOAL_OUTPUT_FORMAT"),\n'
        '  "log_level": os.environ.get("SHOAL_LOG_LEVEL"),\n'
        "}\n"
        "print(json.dumps(payload))\n"
        "sys.exit(0)\n",
    )

    return fin_root


def test_load_manifest_from_root(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    root, manifest = load_fin_manifest(fin_root)
    assert root == fin_root
    assert manifest.name == "example-fin"
    assert manifest.fin_contract_version == 1


def test_load_manifest_rejects_wrong_contract(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    manifest_path = fin_root / "fin.toml"
    manifest_path.write_text(
        manifest_path.read_text().replace("fin_contract_version = 1", "fin_contract_version = 2")
    )

    with pytest.raises(FinRuntimeError, match="Unsupported fin_contract_version"):
        load_fin_manifest(fin_root)


def test_validate_fin_passes_strict_flag(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = validate_fin(fin_root, strict=True)
    assert result.exit_code == 0
    assert "strict-ok" in result.stdout


def test_install_fin_executes_install_entrypoint(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    result = install_fin(fin_root, register=False)
    assert result.exit_code == 0
    assert "install-ok" in result.stdout


def test_configure_fin_passes_config_env(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    cfg = tmp_path / "fin.env"
    cfg.write_text("KEY=VALUE\n")
    result = configure_fin(fin_root, config_path=str(cfg))
    assert result.exit_code == 0
    assert f"configure:{cfg.resolve()}" in result.stdout


def test_run_fin_passes_args_and_env(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    cfg = tmp_path / "fin.env"
    cfg.write_text("KEY=VALUE\n")

    result = run_fin(
        fin_root,
        config_path=str(cfg),
        output_format="json",
        args=["hello", "world"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["args"] == ["hello", "world"]
    assert payload["root"] == str(fin_root)
    assert payload["config"] == str(cfg.resolve())
    assert payload["format"] == "json"


def test_run_fin_includes_shoal_log_level(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    logger = logging.getLogger("shoal")
    original_level = logger.level
    try:
        logger.setLevel(logging.WARNING)
        result = run_fin(fin_root, config_path=None, output_format="json", args=[])
    finally:
        logger.setLevel(original_level)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["log_level"] == "WARNING"


def test_run_fin_non_executable_entrypoint_fails(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    run_path = fin_root / "bin" / "run"
    run_path.chmod(0o644)

    with pytest.raises(FinRuntimeError, match="not executable"):
        run_fin(fin_root, config_path=None, output_format="text", args=[])


def test_list_fins_reports_valid_and_invalid(tmp_path: Path) -> None:
    valid_root = _create_fin(tmp_path)
    invalid_root = tmp_path / "broken-fin"
    invalid_root.mkdir(parents=True)
    (invalid_root / "fin.toml").write_text("name = 'broken'\n")

    items = list_fins(tmp_path)
    by_root = {item.root: item for item in items}

    valid = by_root[str(valid_root)]
    assert valid.status == "valid"
    assert valid.name == "example-fin"

    invalid = by_root[str(invalid_root)]
    assert invalid.status == "invalid"
    assert invalid.error is not None
    assert "Invalid manifest" in invalid.error


# --- register_fin ---


def test_register_fin_copies_directory(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        dest = register_fin(fin_root)

    assert dest == registry / "example-fin"
    assert (dest / "fin.toml").exists()
    assert (dest / "bin" / "install").exists()


def test_register_fin_from_manifest_file(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        dest = register_fin(fin_root / "fin.toml")

    assert dest == registry / "example-fin"
    assert (dest / "fin.toml").exists()


def test_register_fin_is_idempotent(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        register_fin(fin_root)
        dest = register_fin(fin_root)  # second call should not raise

    assert dest == registry / "example-fin"


def test_register_fin_missing_source_raises(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    missing = tmp_path / "does-not-exist"

    with (
        patch("shoal.services.fin_runtime.fins_dir", return_value=registry),
        pytest.raises(FinRuntimeError),
    ):
        register_fin(missing)


# --- list_registered_fins ---


def test_list_registered_fins_empty_when_dir_missing(tmp_path: Path) -> None:
    registry = tmp_path / "registry"  # does not exist

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        items = list_registered_fins()

    assert items == []


def test_list_registered_fins_returns_installed_fin(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        register_fin(fin_root)
        items = list_registered_fins()

    assert len(items) == 1
    assert items[0].name == "example-fin"
    assert items[0].status == "valid"


def test_list_registered_fins_reports_invalid_entry(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    broken = registry / "broken-fin"
    broken.mkdir(parents=True)
    (broken / "fin.toml").write_text("name = 'broken'\n")  # missing required fields

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        items = list_registered_fins()

    assert len(items) == 1
    assert items[0].status == "invalid"


# --- install_fin with register=True ---


def test_install_fin_calls_register_when_register_true(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        result = install_fin(fin_root, register=True)

    assert result.exit_code == 0
    assert (registry / "example-fin" / "fin.toml").exists()


def test_install_fin_skips_register_when_false(tmp_path: Path) -> None:
    fin_root = _create_fin(tmp_path)
    registry = tmp_path / "registry"

    with patch("shoal.services.fin_runtime.fins_dir", return_value=registry):
        result = install_fin(fin_root, register=False)

    assert result.exit_code == 0
    assert not registry.exists()


def test_install_fin_registration_failure_does_not_raise(tmp_path: Path) -> None:
    """A broken register_fin must not propagate — install result still returned."""
    fin_root = _create_fin(tmp_path)

    mock_result = FinExecutionResult(exit_code=0, stdout="install-ok\n", stderr="")

    with (
        patch("shoal.services.fin_runtime.execute_entrypoint", return_value=mock_result),
        patch("shoal.services.fin_runtime.register_fin", side_effect=FinRuntimeError("boom")),
    ):
        result = install_fin(fin_root, register=True)

    assert result.exit_code == 0
    assert result.stdout == "install-ok\n"


# --- timeout ---


def test_execute_entrypoint_raises_on_timeout(tmp_path: Path) -> None:
    """TimeoutExpired from subprocess.run converts to FinRuntimeError."""
    fin_root = _create_fin(tmp_path)
    # Create a slow entrypoint that sleeps longer than the timeout.
    slow_path = fin_root / "bin" / "slow"
    slow_path.write_text("#!/bin/sh\nsleep 10\n")
    slow_path.chmod(0o755)

    with pytest.raises(FinRuntimeError, match="timed out after 0"):
        from shoal.services.fin_runtime import execute_entrypoint

        execute_entrypoint(
            fin_root=fin_root,
            entrypoint=slow_path,
            args=[],
            config_path=None,
            output_format="text",
            timeout=0,  # zero seconds — expires immediately
        )


def test_execute_entrypoint_timeout_none_means_no_limit(tmp_path: Path) -> None:
    """timeout=None passes None to subprocess and does not raise."""
    fin_root = _create_fin(tmp_path)

    with patch("shoal.services.fin_runtime.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        entrypoint = fin_root / "bin" / "run"
        from shoal.services.fin_runtime import execute_entrypoint

        execute_entrypoint(
            fin_root=fin_root,
            entrypoint=entrypoint,
            args=[],
            config_path=None,
            output_format="text",
            timeout=None,
        )

    _call_kwargs = mock_run.call_args.kwargs
    assert _call_kwargs["timeout"] is None


def test_validate_fin_explicit_timeout_overrides_manifest(tmp_path: Path) -> None:
    """Explicit timeout= wins over manifest.default_timeout_seconds."""
    fin_root = _create_fin(tmp_path)
    # Patch manifest to declare a long default.
    _, manifest = load_fin_manifest(fin_root)
    manifest_with_default = manifest.model_copy(update={"default_timeout_seconds": 999})

    with (
        patch(
            "shoal.services.fin_runtime.load_fin_manifest",
            return_value=(fin_root, manifest_with_default),
        ),
        patch("shoal.services.fin_runtime.subprocess.run") as mock_run,
    ):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        validate_fin(fin_root, strict=False, timeout=42)

    assert mock_run.call_args.kwargs["timeout"] == 42


def test_run_fin_uses_manifest_default_when_no_explicit_timeout(tmp_path: Path) -> None:
    """When timeout=None, run_fin falls back to manifest.default_timeout_seconds."""
    fin_root = _create_fin(tmp_path)
    _, manifest = load_fin_manifest(fin_root)
    manifest_with_default = manifest.model_copy(update={"default_timeout_seconds": 30})

    with (
        patch(
            "shoal.services.fin_runtime.load_fin_manifest",
            return_value=(fin_root, manifest_with_default),
        ),
        patch("shoal.services.fin_runtime.subprocess.run") as mock_run,
    ):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        run_fin(fin_root, config_path=None, output_format="text", args=[])

    assert mock_run.call_args.kwargs["timeout"] == 30


def test_install_fin_no_timeout_when_neither_set(tmp_path: Path) -> None:
    """When neither CLI timeout nor manifest default is set, subprocess gets None."""
    fin_root = _create_fin(tmp_path)

    with patch("shoal.services.fin_runtime.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        install_fin(fin_root, register=False, timeout=None)

    assert mock_run.call_args.kwargs["timeout"] is None


def test_manifest_default_timeout_seconds_field(tmp_path: Path) -> None:
    """default_timeout_seconds round-trips through fin.toml parsing."""
    fin_root = _create_fin(tmp_path)
    manifest_path = fin_root / "fin.toml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "[entrypoints]",
            "default_timeout_seconds = 120\n\n[entrypoints]",
        )
    )
    _, manifest = load_fin_manifest(fin_root)
    assert manifest.default_timeout_seconds == 120


def test_manifest_default_timeout_seconds_absent_is_none(tmp_path: Path) -> None:
    """A fin.toml without default_timeout_seconds parses to None."""
    fin_root = _create_fin(tmp_path)
    _, manifest = load_fin_manifest(fin_root)
    assert manifest.default_timeout_seconds is None


# --- _build_env SHOAL_LOG_LEVEL propagation ---


def test_build_env_uses_root_logger_level_when_shoal_is_notset(tmp_path: Path) -> None:
    """When shoal logger has NOTSET, getEffectiveLevel() walks up to root; env var is set.

    SHOAL_LOG_LEVEL is removed from the environment so the parent-override guard
    doesn't mask the root-logger path being tested.
    """
    from shoal.services.fin_runtime import _build_env

    shoal_logger = logging.getLogger("shoal")
    root_logger = logging.getLogger()
    original_shoal = shoal_logger.level
    original_root = root_logger.level
    try:
        shoal_logger.setLevel(logging.NOTSET)  # shoal has no level — inherits root
        root_logger.setLevel(logging.DEBUG)
        with patch.dict("os.environ", {}, clear=False) as env_patch:
            env_patch.pop("SHOAL_LOG_LEVEL", None)  # ensure no parent override
            env = _build_env(fin_root=tmp_path, config_path=None, output_format="text")
    finally:
        shoal_logger.setLevel(original_shoal)
        root_logger.setLevel(original_root)

    assert env["SHOAL_LOG_LEVEL"] == "DEBUG"


def test_build_env_parent_env_overrides_log_level(tmp_path: Path) -> None:
    """Pre-existing SHOAL_LOG_LEVEL in environment is not overwritten."""
    from unittest.mock import patch

    from shoal.services.fin_runtime import _build_env

    shoal_logger = logging.getLogger("shoal")
    original_level = shoal_logger.level
    try:
        shoal_logger.setLevel(logging.WARNING)
        with patch.dict("os.environ", {"SHOAL_LOG_LEVEL": "ERROR"}):
            env = _build_env(fin_root=tmp_path, config_path=None, output_format="text")
    finally:
        shoal_logger.setLevel(original_level)

    # Parent env wins; shoal logger's WARNING is ignored
    assert env["SHOAL_LOG_LEVEL"] == "ERROR"


def test_build_env_omits_log_level_when_fully_notset(tmp_path: Path) -> None:
    """When both shoal and root loggers are NOTSET, env var is omitted."""
    import os

    from shoal.services.fin_runtime import _build_env

    shoal_logger = logging.getLogger("shoal")
    root_logger = logging.getLogger()
    original_shoal = shoal_logger.level
    original_root = root_logger.level
    try:
        shoal_logger.setLevel(logging.NOTSET)
        root_logger.setLevel(logging.NOTSET)
        # Ensure SHOAL_LOG_LEVEL is not in the environment for this call.
        env_without = {k: v for k, v in os.environ.items() if k != "SHOAL_LOG_LEVEL"}
        with patch.dict("os.environ", env_without, clear=True):
            env = _build_env(fin_root=tmp_path, config_path=None, output_format="text")
    finally:
        shoal_logger.setLevel(original_shoal)
        root_logger.setLevel(original_root)

    assert "SHOAL_LOG_LEVEL" not in env
