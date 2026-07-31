from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

import openchem.services.tool_download_service as svc
from openchem.services.tool_download_service import VinaReleaseAsset
from openchem import paths as app_paths


def _fake_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


def test_fetch_latest_vina_release_picks_matching_platform_asset():
    payload = {
        "tag_name": "v1.2.7",
        "assets": [
            {"name": "vina_1.2.7_linux_x86_64", "browser_download_url": "https://x/linux", "size": 111},
            {"name": "vina_1.2.7_win.exe", "browser_download_url": "https://x/win.exe", "size": 222},
            {"name": "vina_1.2.7_mac_x86_64", "browser_download_url": "https://x/mac", "size": 333},
        ],
    }
    with (
        patch.object(svc.platform, "system", return_value="Windows"),
        patch.object(svc, "urlopen", return_value=_fake_response(payload)),
    ):
        asset = svc.fetch_latest_vina_release()

    assert asset == VinaReleaseAsset(
        version="v1.2.7", name="vina_1.2.7_win.exe", download_url="https://x/win.exe", size_bytes=222
    )


def test_fetch_latest_vina_release_skips_checksum_files():
    payload = {
        "tag_name": "v1.2.7",
        "assets": [
            {"name": "vina_1.2.7_win.exe.sha256sum", "browser_download_url": "https://x/checksum", "size": 1},
            {"name": "vina_1.2.7_win.exe", "browser_download_url": "https://x/win.exe", "size": 222},
        ],
    }
    with (
        patch.object(svc.platform, "system", return_value="Windows"),
        patch.object(svc, "urlopen", return_value=_fake_response(payload)),
    ):
        asset = svc.fetch_latest_vina_release()

    assert asset.name == "vina_1.2.7_win.exe"


def test_fetch_latest_vina_release_raises_clear_error_when_no_platform_asset():
    payload = {
        "tag_name": "v1.2.7",
        "assets": [{"name": "vina_1.2.7_mac_x86_64", "browser_download_url": "https://x/mac", "size": 1}],
    }
    with (
        patch.object(svc.platform, "system", return_value="Windows"),
        patch.object(svc, "urlopen", return_value=_fake_response(payload)),
        pytest.raises(RuntimeError, match="No win executable found"),
    ):
        svc.fetch_latest_vina_release()


def test_fetch_latest_vina_release_wraps_network_errors():
    with (
        patch.object(svc, "urlopen", side_effect=URLError("boom")),
        pytest.raises(RuntimeError, match="Could not reach GitHub"),
    ):
        svc.fetch_latest_vina_release()


def test_describe_vina_status_reports_not_found(monkeypatch):
    monkeypatch.setattr(svc, "select_vina_engine", lambda path: None)
    assert svc.describe_vina_status("whatever") == "Not found"


def test_describe_vina_status_reports_engine_id_and_version(monkeypatch):
    class _FakeEngine:
        engine_id = "vina-executable"

        def version(self) -> str:
            return "1.2.7"

    monkeypatch.setattr(svc, "select_vina_engine", lambda path: _FakeEngine())
    assert svc.describe_vina_status("whatever") == "Found: vina-executable 1.2.7"


def test_download_vina_asset_writes_file_to_the_tools_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(tmp_path))

    fake_bytes = b"fake-vina-binary-content"
    chunks = [fake_bytes, b""]
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.headers = {"Content-Length": str(len(fake_bytes))}
    response.read.side_effect = lambda n=-1: chunks.pop(0)

    asset = VinaReleaseAsset(
        version="v1.2.7", name="vina_1.2.7_win.exe", download_url="https://x/win.exe", size_bytes=len(fake_bytes)
    )

    with patch.object(svc, "urlopen", return_value=response):
        result_path = svc.download_vina_asset(asset)

    assert result_path == tmp_path / "tools" / "vina" / "vina_1.2.7_win.exe"
    assert result_path.read_bytes() == fake_bytes


def test_download_vina_asset_cleans_up_partial_file_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(tmp_path))
    asset = VinaReleaseAsset(version="v1", name="broken.exe", download_url="https://x/broken", size_bytes=10)

    with (
        patch.object(svc, "urlopen", side_effect=OSError("boom")),
        pytest.raises(RuntimeError, match="Download failed"),
    ):
        svc.download_vina_asset(asset)

    assert not (tmp_path / "tools" / "vina" / "broken.exe").exists()
