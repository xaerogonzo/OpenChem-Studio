"""The managed Java runtime.

Nothing here downloads: the network parts are exercised by actually
running the installer once, recorded in the commit rather than repeated
on every test run. These pin the decisions around it -- which runtime
wins, how a subprocess is told where it is, and that a machine with Java
already is left alone.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openchem.services import java_setup


def test_a_system_java_is_preferred_over_installing_another(monkeypatch, tmp_path):
    """This is a fallback for machines without Java, not a preference.
    Installing a second runtime beside a working one would waste ~49 MB
    and make version questions harder to answer later."""
    monkeypatch.setattr(java_setup, "system_java_home", lambda: Path("/usr/lib/jvm/real"))

    assert java_setup.java_home() == Path("/usr/lib/jvm/real")
    with pytest.raises(java_setup.JavaSetupError, match="already available"):
        java_setup.install(tmp_path)


def test_the_managed_runtime_is_used_when_there_is_no_system_one(monkeypatch, tmp_path):
    monkeypatch.setattr(java_setup, "system_java_home", lambda: None)
    monkeypatch.setattr(java_setup, "managed_java_home", lambda root=None: tmp_path / "jre")

    assert java_setup.java_home() == tmp_path / "jre"


def test_a_subprocess_environment_carries_java_home_and_path(monkeypatch, tmp_path):
    """jpype finds a JVM through JAVA_HOME or the loader path, and a
    managed runtime is on neither -- so it is injected per subprocess
    rather than exported globally."""
    home = tmp_path / "jre"
    monkeypatch.setattr(java_setup, "java_home", lambda: home)

    environment = java_setup.environment_with_java({"PATH": "/existing"})

    assert environment["JAVA_HOME"] == str(home)
    assert str(home / "bin") in environment["PATH"]
    assert "/existing" in environment["PATH"], "must prepend, not replace"


def test_the_environment_is_untouched_when_there_is_no_java(monkeypatch):
    monkeypatch.setattr(java_setup, "java_home", lambda: None)

    environment = java_setup.environment_with_java({"PATH": "/existing"})

    assert "JAVA_HOME" not in environment
    assert environment["PATH"] == "/existing"


def test_the_download_url_is_the_official_adoptium_api():
    """Verified live: this resolves to
    OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip, 49.0 MB, no key.
    A JRE rather than a JDK -- nothing here compiles Java."""
    url = java_setup.download_url()

    assert url.startswith("https://api.adoptium.net/v3/binary/latest/")
    assert "/jre/" in url
    assert "/eclipse" in url


def test_an_unsupported_platform_says_so_instead_of_building_a_bad_url(monkeypatch):
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Plan9")

    with pytest.raises(java_setup.JavaSetupError, match="No Temurin build"):
        java_setup.download_url()


def test_a_directory_without_a_runtime_is_not_reported_as_one(tmp_path):
    (tmp_path / "not-a-jre").mkdir()

    assert java_setup.managed_java_home(tmp_path) is None


def test_status_explains_what_is_missing_and_what_it_blocks(monkeypatch):
    monkeypatch.setattr(java_setup, "system_java_home", lambda: None)
    monkeypatch.setattr(java_setup, "managed_java_home", lambda root=None: None)

    status = java_setup.describe_status()

    assert "OPSIN" in status
    assert str(java_setup.APPROX_DOWNLOAD_MB) in status


