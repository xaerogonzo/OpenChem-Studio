"""xtb Set Up picks a stable Windows archive and never the bleeding-edge build."""

from openchem.services.tool_download_service import choose_xtb_windows_asset


def test_bleed_is_skipped_and_the_stable_windows_archive_is_kept():
    releases = [
        {
            "tag_name": "bleed",
            "prerelease": True,
            "published_at": "2026-11-01T00:00:00Z",
            "assets": [{"name": "xtb-windows-bleed.zip", "browser_download_url": "https://example.invalid/bleed", "size": 1}],
        },
        {
            "tag_name": "v6.7.1",
            "prerelease": False,
            "published_at": "2026-06-01T00:00:00Z",
            "assets": [
                {"name": "xtb-linux.tar.xz", "browser_download_url": "https://example.invalid/linux", "size": 2},
                {"name": "xtb-6.7.1pre-windows.zip", "browser_download_url": "https://example.invalid/win", "size": 3},
            ],
        },
    ]
    chosen = choose_xtb_windows_asset(releases)
    assert chosen is not None
    assert chosen["name"] == "xtb-6.7.1pre-windows.zip"
    assert chosen["version"] == "v6.7.1"
    assert "pre build" in chosen["caveat"]


def test_no_windows_archive_is_none():
    assert choose_xtb_windows_asset([{"tag_name": "v1", "prerelease": False, "assets": [{"name": "xtb-linux.tar.xz"}]}]) is None
