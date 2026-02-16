"""Tests for new CLI commands: info, rename, logs, init, check."""

from unittest.mock import patch
from typer.testing import CliRunner
from shoal.cli import app
import pytest

runner = CliRunner()

class TestInfo:
    def test_info_not_found(self, mock_dirs):
        result = runner.invoke(app, ["info", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

    def test_info_success(self, mock_dirs):
        from shoal.core.state import create_session
        import asyncio
        asyncio.run(create_session("test-session", "claude", "/tmp/repo"))
        
        result = runner.invoke(app, ["info", "test-session"])
        assert result.exit_code == 0
        assert "Session: test-session" in result.output
        assert "claude" in result.output

class TestRename:
    def test_rename_success(self, mock_dirs):
        from shoal.core.state import create_session, find_by_name
        import asyncio
        asyncio.run(create_session("old-name", "claude", "/tmp/repo"))
        
        with patch("shoal.core.tmux.has_session", return_value=False):
            result = runner.invoke(app, ["rename", "old-name", "new-name"])
            
        assert result.exit_code == 0
        assert "Renamed session: old-name → new-name" in result.output
        
        assert asyncio.run(find_by_name("new-name")) is not None
        assert asyncio.run(find_by_name("old-name")) is None

    def test_rename_not_found(self, mock_dirs):
        result = runner.invoke(app, ["rename", "nonexistent", "new"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

class TestLogs:
    def test_logs_not_found(self, mock_dirs):
        result = runner.invoke(app, ["logs", "nonexistent"])
        assert result.exit_code == 1
        assert "Session not found" in result.output

class TestCheck:
    def test_check_command(self, mock_dirs):
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "Dependency Check" in result.output
        assert "Directories" in result.output

class TestInit:
    def test_init_command(self, mock_dirs, tmp_path):
        # We need to ensure example_src exists for a full test, 
        # but even without it, it should finish successfully.
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Shoal initialized successfully" in result.output
