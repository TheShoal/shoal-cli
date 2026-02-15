"""Tests for services/status_bar.py."""


from shoal.models.state import SessionStatus
from shoal.services.status_bar import generate_status


class TestGenerateStatus:
    def test_empty(self, mock_dirs):
        assert generate_status() == ""

    def test_with_sessions(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = create_session("test-session", "claude", "/tmp")
        update_session(s.id, status=SessionStatus.running)

        result = generate_status()
        assert "test-session" in result
        assert "running" in result
        assert "#[fg=green]" in result
        assert "⚡ 1 active" in result

    def test_stopped_excluded(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = create_session("stopped-one", "claude", "/tmp")
        update_session(s.id, status=SessionStatus.stopped)

        assert generate_status() == ""

    def test_waiting_style(self, mock_dirs):
        from shoal.core.state import create_session, update_session

        s = create_session("waiting-one", "claude", "/tmp")
        update_session(s.id, status=SessionStatus.waiting)

        result = generate_status()
        assert "#[fg=yellow,bold]" in result
