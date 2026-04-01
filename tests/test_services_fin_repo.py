import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from shoal.models.fin import FinSource
from shoal.services.fin_repo import download_fin, registry_url, resolve_fin


def test_registry_url():
    # test latest
    assert (
        registry_url("fin:foo", "https://fins.shoal.dev")
        == "https://fins.shoal.dev/foo/latest.tar.gz"
    )
    # test versioned
    assert (
        registry_url("fin:foo@1.0.0", "https://fins.shoal.dev")
        == "https://fins.shoal.dev/foo/1.0.0.tar.gz"
    )
    # test empty version
    assert (
        registry_url("fin:foo@", "https://fins.shoal.dev")
        == "https://fins.shoal.dev/foo/latest.tar.gz"
    )


def test_resolve_fin_local():
    source = FinSource(raw="/tmp/local", kind="local")
    assert resolve_fin(source) == Path("/tmp/local")


@patch("shoal.services.fin_repo.download_fin")
def test_resolve_fin_http(mock_download_fin):
    mock_download_fin.return_value = Path("/tmp/downloaded")
    source = FinSource(raw="https://example.com/foo.tar.gz", kind="http")
    assert resolve_fin(source) == Path("/tmp/downloaded")
    mock_download_fin.assert_called_once_with("https://example.com/foo.tar.gz")


@patch("shoal.services.fin_repo.download_fin")
@patch("shoal.services.fin_repo.registry_url")
def test_resolve_fin_registry(mock_registry_url, mock_download_fin):
    mock_registry_url.return_value = "https://fins.shoal.dev/foo/latest.tar.gz"
    mock_download_fin.return_value = Path("/tmp/downloaded")
    source = FinSource(raw="fin:foo", kind="registry")
    assert resolve_fin(source, "https://fins.shoal.dev") == Path("/tmp/downloaded")
    mock_registry_url.assert_called_once_with("fin:foo", "https://fins.shoal.dev")
    mock_download_fin.assert_called_once_with("https://fins.shoal.dev/foo/latest.tar.gz")


def test_resolve_fin_invalid_kind():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FinSource(raw="foo", kind="invalid")  # type: ignore


@patch("shoal.services.fin_repo.shutil")
@patch("httpx.stream")
def test_download_fin_success_tar_gz(mock_stream, mock_shutil, tmp_path):
    os.environ["XDG_DATA_HOME"] = str(tmp_path)

    mock_response = MagicMock()
    mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]

    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_response
    mock_stream.return_value = mock_context_manager

    url = "https://example.com/foo.tar.gz"

    dest = download_fin(url)

    expected_dest = tmp_path / "shoal" / "fins" / "_downloads" / "foo"
    assert dest == expected_dest

    mock_stream.assert_called_once_with("GET", url, follow_redirects=True, timeout=30)
    mock_response.raise_for_status.assert_called_once()
    mock_shutil.unpack_archive.assert_called_once()


@patch("shoal.services.fin_repo.shutil")
@patch("httpx.stream")
def test_download_fin_success_zip(mock_stream, mock_shutil, tmp_path):
    os.environ["XDG_DATA_HOME"] = str(tmp_path)

    mock_response = MagicMock()
    mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]

    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_response
    mock_stream.return_value = mock_context_manager

    url = "https://example.com/bar.zip"

    dest = download_fin(url)

    expected_dest = tmp_path / "shoal" / "fins" / "_downloads" / "bar"
    assert dest == expected_dest

    mock_stream.assert_called_once_with("GET", url, follow_redirects=True, timeout=30)


def test_download_fin_invalid_extension():
    url = "https://example.com/foo.txt"
    with pytest.raises(ValueError, match=r"Unsupported archive extension for fin download.*"):
        download_fin(url)


@patch("httpx.stream")
def test_download_fin_http_error(mock_stream, tmp_path):
    os.environ["XDG_DATA_HOME"] = str(tmp_path)

    mock_context_manager = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 404
    exc = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)

    mock_context_manager.__enter__.side_effect = exc
    mock_stream.return_value = mock_context_manager
    httpx.HTTPStatusError = httpx.HTTPStatusError

    url = "https://example.com/foo.tar.gz"

    with pytest.raises(ValueError, match=r"Failed to download fin: HTTP 404 from.*"):
        download_fin(url)


@patch("httpx.stream")
def test_download_fin_network_error(mock_stream, tmp_path):
    os.environ["XDG_DATA_HOME"] = str(tmp_path)

    mock_context_manager = MagicMock()
    exc = httpx.RequestError("Network error")

    mock_context_manager.__enter__.side_effect = exc
    mock_stream.return_value = mock_context_manager
    httpx.HTTPError = httpx.HTTPError

    url = "https://example.com/foo.tar.gz"

    with pytest.raises(ValueError, match="Failed to download fin: Network error"):
        download_fin(url)
