from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from shoal.cli.handoff import handoff_ls, handoff_show
from shoal.core.journal import HandoffArtifact
from shoal.core.state import SessionState

runner = CliRunner()


@pytest.fixture
def mock_console():
    with patch("shoal.cli.handoff.get_console") as mock:
        yield mock.return_value


@pytest.fixture
def mock_resolve_session():
    with patch(
        "shoal.core.state._resolve_session_interactive_impl", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_get_session():
    with patch("shoal.core.state.get_session", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_read_journal():
    with patch("shoal.cli.handoff.read_journal") as mock:
        mock.return_value = []
        yield mock


@pytest.fixture
def mock_db():
    with patch("shoal.core.db.get_db", new_callable=AsyncMock) as mock:
        db_mock = AsyncMock()
        db_mock.get_status_transitions.return_value = []
        mock.return_value = db_mock
        yield mock


@pytest.fixture
def mock_generate_handoff():
    with patch("shoal.cli.handoff.generate_handoff") as mock:
        artifact = MagicMock(spec=HandoffArtifact)
        artifact.to_dict.return_value = {"status": "ok"}
        artifact.to_markdown.return_value = "## Status OK"
        mock.return_value = artifact
        yield mock


@pytest.fixture
def mock_write_handoff():
    with patch("shoal.cli.handoff.write_handoff_artifact") as mock:
        mock.return_value = Path("/tmp/handoff.md")
        yield mock


def test_handoff_show_not_found(mock_resolve_session, mock_console):
    mock_resolve_session.return_value = None
    import typer

    with pytest.raises(typer.Exit):
        handoff_show("unknown")
    mock_console.print.assert_called_with("[red]Session 'unknown' not found[/red]")


def test_handoff_show_not_in_db(mock_resolve_session, mock_get_session, mock_console):
    mock_resolve_session.return_value = "sid"
    mock_get_session.return_value = None
    import typer

    with pytest.raises(typer.Exit):
        handoff_show("sid")
    mock_console.print.assert_called_with("[red]Session 'sid' not found in DB[/red]")


def test_handoff_show_success_markdown(
    mock_resolve_session,
    mock_get_session,
    mock_read_journal,
    mock_db,
    mock_generate_handoff,
    mock_console,
):
    mock_resolve_session.return_value = "sid"
    mock_get_session.return_value = MagicMock(spec=SessionState)

    handoff_show("sid")

    mock_console.print.assert_called()
    assert mock_console.print.call_args[0][0].__class__.__name__ == "Markdown"


def test_handoff_show_success_json(
    mock_resolve_session,
    mock_get_session,
    mock_read_journal,
    mock_db,
    mock_generate_handoff,
    mock_console,
):
    mock_resolve_session.return_value = "sid"
    mock_get_session.return_value = MagicMock(spec=SessionState)

    handoff_show("sid", as_json=True)

    mock_console.print_json.assert_called_with('{"status": "ok"}')


def test_handoff_show_success_save(
    mock_resolve_session,
    mock_get_session,
    mock_read_journal,
    mock_db,
    mock_generate_handoff,
    mock_write_handoff,
    mock_console,
):
    mock_resolve_session.return_value = "sid"
    mock_get_session.return_value = MagicMock(spec=SessionState)

    handoff_show("sid", save=True)

    mock_write_handoff.assert_called_once_with("sid", mock_generate_handoff.return_value)
    mock_console.print.assert_any_call("[green]Saved:[/green] /tmp/handoff.md")


@patch("shoal.core.journal._journals_dir")
def test_handoff_ls_no_dir(mock_journals_dir, mock_console):
    mock_dir = MagicMock(spec=Path)
    mock_dir.exists.return_value = False
    mock_journals_dir.return_value.__truediv__.return_value = mock_dir

    handoff_ls()

    mock_console.print.assert_called_with("[dim]No handoff artifacts found.[/dim]")


@patch("shoal.core.journal._journals_dir")
def test_handoff_ls_no_files(mock_journals_dir, mock_console):
    mock_dir = MagicMock(spec=Path)
    mock_dir.exists.return_value = True
    mock_dir.glob.return_value = []
    mock_journals_dir.return_value.__truediv__.return_value = mock_dir

    handoff_ls()

    mock_console.print.assert_called_with("[dim]No handoff artifacts found.[/dim]")


@patch("shoal.core.journal._journals_dir")
def test_handoff_ls_with_files(mock_journals_dir, mock_console):
    mock_dir = MagicMock(spec=Path)
    mock_dir.exists.return_value = True

    mock_file = MagicMock(spec=Path)
    mock_file.stem = "sid"
    mock_stat = MagicMock()
    mock_stat.st_mtime = 1600000000
    mock_stat.st_size = 1000
    mock_file.stat.return_value = mock_stat

    mock_dir.glob.return_value = [mock_file]
    mock_journals_dir.return_value.__truediv__.return_value = mock_dir

    handoff_ls()

    mock_console.print.assert_called()
    assert mock_console.print.call_args[0][0].__class__.__name__ == "Table"
