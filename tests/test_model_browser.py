"""Tests for justllama.models.browser.ModelBrowser and ModelInfo.

All tests are self-contained — no server, GPU, or network needed.
"""

from pathlib import Path

import pytest

from justllama.models.browser import ModelBrowser, ModelInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _qapp():
    """Ensure a QCoreApplication exists (PySide6 QObject requirement)."""
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def browser(_qapp, tmp_path):
    """ModelBrowser rooted at a fresh temp directory."""
    return ModelBrowser(models_dir=str(tmp_path))


def _write_gguf(path: Path, size: int = 1024) -> Path:
    """Create a fake .gguf file of *size* bytes and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


# ---------------------------------------------------------------------------
# scan() tests
# ---------------------------------------------------------------------------

def test_scan_finds_gguf_files(browser, tmp_path):
    """scan() discovers .gguf files but skips mmproj projectors."""
    _write_gguf(tmp_path / "model1.gguf", size=2048)
    _write_gguf(tmp_path / "model2.gguf", size=4096)
    _write_gguf(tmp_path / "mmproj-F32.gguf", size=1024)

    results = browser.scan()

    names = [m["name"] for m in results]
    assert sorted(names) == ["model1", "model2"]
    assert all(m["size_bytes"] > 0 for m in results)


def test_scan_empty_directory(browser):
    """Empty directory yields no models."""
    assert browser.scan() == []


def test_scan_missing_directory():
    """Non-existent directory does not crash — returns []."""
    browser = ModelBrowser(models_dir="/no/such/path/ever")
    assert browser.scan() == []


def test_scan_non_gguf_ignored(browser, tmp_path):
    """Non-.gguf files are silently skipped."""
    (tmp_path / "model.bin").write_bytes(b"\x00" * 100)
    (tmp_path / "readme.txt").write_text("hello")

    assert browser.scan() == []


# ---------------------------------------------------------------------------
# get_model() tests
# ---------------------------------------------------------------------------

def test_get_model(browser, tmp_path):
    """get_model() returns correct metadata for an existing file."""
    f = _write_gguf(tmp_path / "alpha.gguf", size=500)

    result = browser.get_model(str(f))

    assert result is not None
    assert result["name"] == "alpha"
    assert result["path"] == str(f)
    assert result["size_bytes"] == 500


def test_get_model_missing(browser):
    """get_model() returns None for a path that does not exist."""
    assert browser.get_model("/nonexistent/model.gguf") is None


# ---------------------------------------------------------------------------
# set_directory() tests
# ---------------------------------------------------------------------------

def test_set_directory(browser, tmp_path):
    """Changing the directory changes what scan() finds."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    _write_gguf(dir_a / "only_in_a.gguf")
    _write_gguf(dir_b / "only_in_b.gguf")

    # Start points at tmp_path (no .gguf there)
    assert browser.scan() == []

    browser.set_directory(str(dir_a))
    names_a = [m["name"] for m in browser.scan()]
    assert names_a == ["only_in_a"]

    browser.set_directory(str(dir_b))
    names_b = [m["name"] for m in browser.scan()]
    assert names_b == ["only_in_b"]


# ---------------------------------------------------------------------------
# ModelInfo unit tests
# ---------------------------------------------------------------------------

def test_model_info_size_display():
    """size_display formats 1.5 GB (≈1 610 612 736 B) with 'GB'."""
    size_1_5gb = int(1.5 * 1024 * 1024 * 1024)
    info = ModelInfo(name="big", path="/big.gguf", size_bytes=size_1_5gb, modified_time=0.0)

    display = info.size_display

    assert "GB" in display
    assert "1.5" in display


def test_model_info_to_dict():
    """to_dict() contains every expected key and round-trips values."""
    info = ModelInfo(name="m", path="/m.gguf", size_bytes=512, modified_time=1000.0)
    d = info.to_dict()

    expected_keys = {"name", "path", "size_bytes", "size_display", "modified_time"}
    assert set(d.keys()) == expected_keys
    assert d["name"] == "m"
    assert d["path"] == "/m.gguf"
    assert d["size_bytes"] == 512
    assert d["modified_time"] == 1000.0
    assert isinstance(d["size_display"], str)
