"""Tests for justllama.models.profiles.ModelProfiles.

All file I/O is redirected to a temp directory via monkeypatching the
module-level ``_PROFILES_DIR`` so the real ``~/.config/justllama/profiles/``
is never touched.
"""

import json

import pytest

from justllama.models.profiles import ModelProfiles


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _qapp():
    """Ensure a QCoreApplication exists (PySide6 QObject requirement)."""
    from PySide6.QtCore import QCoreApplication
    import sys

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


@pytest.fixture
def profiles_dir(tmp_path):
    """Return a fresh subdirectory inside tmp_path to act as profiles dir."""
    d = tmp_path / "profiles"
    d.mkdir()
    return d


@pytest.fixture
def profiles(_qapp, profiles_dir, monkeypatch):
    """ModelProfiles instance rooted at a temp directory."""
    monkeypatch.setattr(
        "justllama.models.profiles._PROFILES_DIR", profiles_dir
    )
    return ModelProfiles()


def _save_json(path: str, data: dict) -> None:
    """Helper to write a JSON file directly."""
    from pathlib import Path

    Path(path).write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# save_profile() tests
# ---------------------------------------------------------------------------

class TestSaveProfile:
    def test_saves_valid_json(self, profiles, profiles_dir):
        """Writing a valid JSON string creates the profile on disk."""
        config = {"port": 8080, "model_path": "/models/test.gguf"}
        result = profiles.save_profile("fast-chat", json.dumps(config))

        assert result is True
        saved = profiles_dir / "fast-chat.json"
        assert saved.is_file()
        assert json.loads(saved.read_text()) == config

    def test_returns_false_for_invalid_json(self, profiles):
        """Malformed JSON string is rejected without writing a file."""
        result = profiles.save_profile("bad", "{not valid json")

        assert result is False

    def test_emits_profiles_changed_signal(self, profiles):
        """Successful save emits profiles_changed."""
        spy = []
        profiles.profiles_changed.connect(lambda: spy.append(True))

        profiles.save_profile("sig-test", '{"x": 1}')

        assert len(spy) == 1

    def test_creates_file_on_disk(self, profiles, profiles_dir):
        """After save_profile the file exists at the expected path."""
        profiles.save_profile("disk-check", '{"a": "b"}')

        expected = profiles_dir / "disk-check.json"
        assert expected.exists()
        assert expected.read_text().strip() != ""

    def test_overwrites_existing_profile(self, profiles, profiles_dir):
        """Saving with the same name replaces the old content."""
        profiles.save_profile("overwrite", '{"version": 1}')
        profiles.save_profile("overwrite", '{"version": 2}')

        data = json.loads((profiles_dir / "overwrite.json").read_text())
        assert data == {"version": 2}

    def test_empty_name_saves_file(self, profiles, profiles_dir):
        """An empty name still produces a file (name is valid string)."""
        result = profiles.save_profile("", '{"empty": true}')
        assert result is True
        assert (profiles_dir / ".json").is_file()

    def test_nested_json_structure(self, profiles, profiles_dir):
        """Deeply nested config dicts survive round-trip."""
        config = {"l1": {"l2": {"l3": [1, 2, 3]}}}
        profiles.save_profile("deep", json.dumps(config))

        loaded = json.loads((profiles_dir / "deep.json").read_text())
        assert loaded == config


# ---------------------------------------------------------------------------
# load_profile() tests
# ---------------------------------------------------------------------------

class TestLoadProfile:
    def test_loads_existing_profile(self, profiles, profiles_dir):
        """load_profile returns the JSON string for an existing profile."""
        config = {"key": "value"}
        _save_json(str(profiles_dir / "myprofile.json"), config)

        result = profiles.load_profile("myprofile")
        assert result != ""
        assert json.loads(result) == config

    def test_returns_empty_string_for_missing(self, profiles):
        """Non-existent profile returns empty string."""
        result = profiles.load_profile("no-such-profile")
        assert result == ""

    def test_returns_valid_json(self, profiles, profiles_dir):
        """Loaded output is valid JSON that can be parsed."""
        _save_json(str(profiles_dir / "valid.json"), {"a": 1})
        raw = profiles.load_profile("valid")

        # Should not raise
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_load_after_save(self, profiles):
        """Round-trip: save then load returns identical data."""
        config = {"ctx_size": 4096, "threads": 8}
        profiles.save_profile("roundtrip", json.dumps(config))

        loaded = json.loads(profiles.load_profile("roundtrip"))
        assert loaded == config

    def test_load_preserves_string_values(self, profiles, profiles_dir):
        """String values survive the load round-trip."""
        _save_json(str(profiles_dir / "str.json"), {"path": "/a/b/c"})
        data = json.loads(profiles.load_profile("str"))
        assert data["path"] == "/a/b/c"


# ---------------------------------------------------------------------------
# list_profiles() tests
# ---------------------------------------------------------------------------

class TestListProfiles:
    def test_empty_when_no_profiles(self, profiles):
        """No files → empty list."""
        assert profiles.list_profiles() == []

    def test_returns_sorted_list(self, profiles, profiles_dir):
        """Profile names are returned in sorted order."""
        _save_json(str(profiles_dir / "zebra.json"), {"z": 1})
        _save_json(str(profiles_dir / "alpha.json"), {"a": 1})
        _save_json(str(profiles_dir / "middle.json"), {"m": 1})

        result = profiles.list_profiles()
        assert result == ["alpha", "middle", "zebra"]

    def test_only_includes_json_files(self, profiles, profiles_dir):
        """Non-.json files in the directory are ignored."""
        _save_json(str(profiles_dir / "valid.json"), {"ok": 1})
        (profiles_dir / "notes.txt").write_text("not a profile")
        (profiles_dir / "data.yaml").write_text("key: value")
        (profiles_dir / ".hidden").write_text("dotfile")

        result = profiles.list_profiles()
        assert result == ["valid"]

    def test_single_profile(self, profiles, profiles_dir):
        """One profile returns a list of length 1."""
        _save_json(str(profiles_dir / "solo.json"), {"solo": True})
        assert profiles.list_profiles() == ["solo"]

    def test_list_empty_after_delete(self, profiles, profiles_dir):
        """Deleting the only profile makes list_profiles return []."""
        _save_json(str(profiles_dir / "temp.json"), {"tmp": 1})
        profiles.delete_profile("temp")
        assert profiles.list_profiles() == []


# ---------------------------------------------------------------------------
# delete_profile() tests
# ---------------------------------------------------------------------------

class TestDeleteProfile:
    def test_deletes_existing_profile(self, profiles, profiles_dir):
        """Deleting an existing profile returns True."""
        _save_json(str(profiles_dir / "to_delete.json"), {"del": 1})
        result = profiles.delete_profile("to_delete")

        assert result is True
        assert not (profiles_dir / "to_delete.json").is_file()

    def test_returns_false_for_nonexistent(self, profiles):
        """Deleting a profile that doesn't exist returns False."""
        result = profiles.delete_profile("ghost")
        assert result is False

    def test_emits_profiles_changed_signal(self, profiles, profiles_dir):
        """Successful delete emits profiles_changed."""
        _save_json(str(profiles_dir / "sig_del.json"), {"x": 1})
        spy = []
        profiles.profiles_changed.connect(lambda: spy.append(True))

        profiles.delete_profile("sig_del")

        assert len(spy) == 1

    def test_file_removed_from_disk(self, profiles, profiles_dir):
        """After delete_profile, the .json file no longer exists."""
        _save_json(str(profiles_dir / "gone.json"), {"bye": 1})
        profiles.delete_profile("gone")

        assert not (profiles_dir / "gone.json").exists()

    def test_delete_does_not_affect_other_profiles(self, profiles, profiles_dir):
        """Deleting one profile leaves the others intact."""
        _save_json(str(profiles_dir / "keep.json"), {"k": 1})
        _save_json(str(profiles_dir / "drop.json"), {"d": 1})

        profiles.delete_profile("drop")

        assert profiles.list_profiles() == ["keep"]

    def test_signal_not_emitted_for_missing(self, profiles):
        """No signal when deleting a non-existent profile."""
        spy = []
        profiles.profiles_changed.connect(lambda: spy.append(True))

        profiles.delete_profile("no-such-name")

        assert len(spy) == 0


# ---------------------------------------------------------------------------
# _path_for() tests
# ---------------------------------------------------------------------------

class TestPathFor:
    def test_sanitizes_slashes(self, profiles, profiles_dir):
        """Slashes in names are replaced with underscores."""
        result = profiles._path_for("foo/bar")
        assert result.name == "foo_bar.json"

    def test_sanitizes_dot_dot(self, profiles, profiles_dir):
        """Parent directory references (..) are replaced with underscores."""
        result = profiles._path_for("..etc..passwd")
        assert result.name == "_etc_passwd.json"

    def test_clean_name_unchanged(self, profiles, profiles_dir):
        """A clean name produces exactly ``<name>.json``."""
        result = profiles._path_for("my-model")
        assert result.name == "my-model.json"

    def test_combined_slash_and_dotdot(self, profiles, profiles_dir):
        """Both slashes and dotdot are sanitized in one call."""
        result = profiles._path_for("../../etc/passwd")
        assert result.name == "____etc_passwd.json"

    def test_result_is_path_under_profiles_dir(self, profiles, profiles_dir):
        """_path_for always returns a path inside the profiles directory."""
        result = profiles._path_for("anything")
        assert result.parent == profiles_dir

    def test_preserves_underscores(self, profiles, profiles_dir):
        """Underscores in the original name are kept as-is."""
        result = profiles._path_for("my_profile_v2")
        assert result.name == "my_profile_v2.json"

    def test_unicode_name(self, profiles, profiles_dir):
        """Unicode characters in the name are preserved."""
        result = profiles._path_for("日本語モデル")
        assert result.name == "日本語モデル.json"


# ---------------------------------------------------------------------------
# get_model_profile() & get_effective_config() tests
# ---------------------------------------------------------------------------

class TestModelProfileConfig:
    def test_get_and_save_model_profile(self, profiles):
        model_path = "/models/llama-3-8b.gguf"
        data = {"jinja": True, "ctx_size": 8192, "flash_attn": "auto"}
        assert profiles.save_model_profile(model_path, json.dumps(data)) is True

        loaded = profiles.get_model_profile(model_path)
        assert loaded["jinja"] is True
        assert loaded["ctx_size"] == 8192
        assert loaded["flash_attn"] == "auto"

    def test_get_effective_config_merges_defaults_and_overrides(self, profiles):
        model_path = "/models/deepseek-r1.gguf"
        profiles.save_model_profile(model_path, json.dumps({"jinja": True, "extra_args": ["--rope-scaling", "linear"]}))

        eff = profiles.get_effective_config(model_path, None)
        assert eff["model_path"] == model_path
        assert eff["jinja"] is True
        assert eff["extra_args"] == ["--rope-scaling", "linear"]
        assert eff["ctx_size"] == 4096
        assert eff["n_gpu_layers"] == "auto"
