import subprocess
from unittest.mock import patch, MagicMock

from justllama.server.skills.context7_skill import Context7LibrarySkill, Context7DocsSkill


def test_context7_library_success():
    skill = Context7LibrarySkill()
    assert skill.get_name() == "context7_library"
    assert "Resolves" in skill.get_description()
    assert skill.timeout == 60.0

    mock_run = MagicMock()
    mock_run.return_value.stdout = "1. Title: React\nContext7-compatible library ID: /react/react"

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", mock_run):
        res = skill.execute({"name": "react", "query": "useEffect"})
        assert "/react/react" in res
        mock_run.assert_called_once_with(
            ["npx", "ctx7@latest", "library", "react", "useEffect"],
            capture_output=True,
            text=True,
            check=True
        )


def test_context7_library_missing_args():
    skill = Context7LibrarySkill()
    res = skill.execute({"name": "", "query": ""})
    assert "Error" in res


def test_context7_library_missing_npx():
    skill = Context7LibrarySkill()
    with patch("shutil.which", return_value=None):
        res = skill.execute({"name": "react", "query": "useEffect"})
        assert "npx' command not found" in res


def test_context7_library_command_error():
    skill = Context7LibrarySkill()
    mock_run = MagicMock(side_effect=subprocess.CalledProcessError(1, cmd=["npx"], stderr="Network timeout"))

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", mock_run):
        res = skill.execute({"name": "react", "query": "useEffect"})
        assert "Network timeout" in res


def test_context7_docs_success():
    skill = Context7DocsSkill()
    assert skill.get_name() == "context7_docs"
    assert "Fetches" in skill.get_description()
    assert skill.timeout == 60.0

    mock_run = MagicMock()
    mock_run.return_value.stdout = "useEffect: Performs side effects"

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", mock_run):
        res = skill.execute({"library_id": "/react/react", "query": "useEffect cleanup"})
        assert "side effects" in res
        mock_run.assert_called_once_with(
            ["npx", "ctx7@latest", "docs", "/react/react", "useEffect cleanup"],
            capture_output=True,
            text=True,
            check=True
        )


def test_context7_docs_missing_args():
    skill = Context7DocsSkill()
    res = skill.execute({"library_id": "", "query": ""})
    assert "Error" in res


def test_context7_docs_missing_npx():
    skill = Context7DocsSkill()
    with patch("shutil.which", return_value=None):
        res = skill.execute({"library_id": "/react/react", "query": "useEffect"})
        assert "npx' command not found" in res


def test_context7_docs_command_error():
    skill = Context7DocsSkill()
    mock_run = MagicMock(side_effect=subprocess.CalledProcessError(1, cmd=["npx"], stderr="Library not found"))

    with patch("shutil.which", return_value="/usr/bin/npx"), \
         patch("subprocess.run", mock_run):
        res = skill.execute({"library_id": "/react/react", "query": "useEffect"})
        assert "Library not found" in res
