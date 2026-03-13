"""Tests for conflict marker detection in .ai-guard files."""

import pytest

from ai_guard.cli import main
from ai_guard.core import GuardFile


class TestConflictDetection:
    """Commands are blocked when .ai-guard has merge conflict markers."""

    def _write_conflicted_guard(self, temp_project):
        """Write an .ai-guard file with conflict markers."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        content = (
            ".ai-guard:0000000000000000\n"
            "<<<<<<< HEAD\n"
            "config.py:aaaa111122223333\n"
            "=======\n"
            "config.py:bbbb444455556666\n"
            ">>>>>>> other-branch\n"
        )
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

    def test_has_conflicts_flag_set(self, temp_project):
        """GuardFile.has_conflicts is True when markers are present."""
        self._write_conflicted_guard(temp_project)
        guard = GuardFile(temp_project)
        assert guard.has_conflicts is True

    def test_has_conflicts_flag_clear(self, temp_project):
        """GuardFile.has_conflicts is False for a clean file."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        guard2 = GuardFile(temp_project)
        assert guard2.has_conflicts is False

    def test_add_blocked(self, temp_project, monkeypatch):
        """'add' is blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["add", "config.py"])
        assert result == 1

    def test_update_blocked(self, temp_project, monkeypatch):
        """'update' is blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["update", "--all"])
        assert result == 1

    def test_remove_blocked(self, temp_project, monkeypatch):
        """'remove' is blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["remove", "config.py"])
        assert result == 1

    def test_verify_blocked(self, temp_project, monkeypatch):
        """'verify' is blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["verify"])
        assert result == 1

    def test_list_blocked(self, temp_project, monkeypatch):
        """'list' is blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["list"])
        assert result == 1

    def test_resolve_not_blocked(self, temp_project, monkeypatch):
        """'resolve' is NOT blocked when .ai-guard has conflict markers."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        result = main(["resolve"])
        assert result == 0

    def test_diff3_markers_detected(self, temp_project):
        """diff3-style markers (with |||||||) are also detected."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        content = (
            ".ai-guard:0000000000000000\n"
            "<<<<<<< HEAD\n"
            "config.py:aaaa111122223333\n"
            "||||||| merged common ancestors\n"
            "config.py:cccc777788889999\n"
            "=======\n"
            "config.py:bbbb444455556666\n"
            ">>>>>>> other-branch\n"
        )
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        assert guard.has_conflicts is True

    def test_error_message_mentions_resolve(self, temp_project, monkeypatch, capsys):
        """The error message tells the user to run 'ai-guard resolve'."""
        self._write_conflicted_guard(temp_project)
        monkeypatch.chdir(temp_project)
        main(["verify"])
        captured = capsys.readouterr()
        assert "ai-guard resolve" in captured.err
