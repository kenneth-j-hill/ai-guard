"""Tests for the resolve subcommand."""

import pytest

from ai_guard.cli import main
from ai_guard.core import GuardFile, compute_file_hash, compute_identifier_hash


class TestResolveClean:
    """Resolve with no conflict markers — just recomputes hashes."""

    def test_recomputes_stale_hash(self, temp_project):
        """Resolve recomputes hashes from the working tree."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Modify the file (simulating post-merge state)
        filepath.write_text("SECRET = 99\n", encoding="utf-8")

        guard2 = GuardFile(temp_project)
        resolved, conflicted = guard2.resolve()
        assert conflicted == []
        assert len(resolved) == 1
        assert resolved[0].hash == compute_file_hash(filepath)

    def test_drops_missing_file(self, temp_project):
        """Resolve drops entries for files that no longer exist."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.save()

        # Delete the file
        filepath.unlink()

        guard2 = GuardFile(temp_project)
        resolved, conflicted = guard2.resolve()
        assert conflicted == []
        assert len(resolved) == 0

    def test_drops_missing_identifier(self, temp_project, sample_python_file):
        """Resolve drops entries for identifiers that no longer exist."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        # Rewrite the file without that function
        sample_python_file.write_text("def other_function():\n    pass\n", encoding="utf-8")

        guard2 = GuardFile(temp_project)
        resolved, conflicted = guard2.resolve()
        assert conflicted == []
        assert len(resolved) == 0


class TestResolveTwoWayConflict:
    """Resolve with 2-way conflict markers."""

    def test_parses_both_sides(self, temp_project):
        """Entries from both sides of a conflict are parsed."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")
        other = temp_project / "other.py"
        other.write_text("VALUE = 1\n", encoding="utf-8")

        content = (
            "<<<<<<< HEAD\n"
            "config.py:aaaa111122223333\n"
            "=======\n"
            "other.py:bbbb444455556666\n"
            ">>>>>>> other-branch\n"
        )
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        resolved, conflicted = guard.resolve()
        assert conflicted == []
        paths = {e.path for e in resolved}
        assert paths == {"config.py", "other.py"}

    def test_same_target_different_hashes(self, temp_project):
        """Same target with different hashes on both sides — recomputed from disk."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")

        content = (
            "<<<<<<< HEAD\n"
            "config.py:aaaa111122223333\n"
            "=======\n"
            "config.py:bbbb444455556666\n"
            ">>>>>>> other-branch\n"
        )
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        resolved, conflicted = guard.resolve()
        assert len(resolved) == 1
        assert resolved[0].hash == compute_file_hash(config)


class TestResolveThreeWayConflict:
    """Resolve with 3-way diff3 conflict markers."""

    def test_parses_diff3_markers(self, temp_project):
        """diff3 markers (with |||||||) are handled correctly."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")

        content = (
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
        resolved, conflicted = guard.resolve()
        assert len(resolved) == 1
        assert resolved[0].hash == compute_file_hash(config)


class TestResolveIdentifiers:
    """Resolve with identifier-level entries."""

    def test_recomputes_identifier_hash(self, temp_project, sample_python_file):
        """Identifier hashes are recomputed from the working tree."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        # Modify the function
        source = sample_python_file.read_text(encoding="utf-8")
        source = source.replace("return 1", "return 2")
        sample_python_file.write_text(source, encoding="utf-8")

        guard2 = GuardFile(temp_project)
        resolved, conflicted = guard2.resolve()
        assert len(resolved) == 1
        assert resolved[0].identifier == "simple_function"
        assert resolved[0].hash == compute_identifier_hash(sample_python_file, "simple_function")

    def test_mixed_file_and_identifier_entries(self, temp_project, sample_python_file):
        """Both file-level and identifier-level entries are resolved."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")

        guard = GuardFile(temp_project)
        guard.add_file("config.py")
        guard.add_identifier("sample.py", "simple_function")
        guard.save()

        # Modify both
        config.write_text("SECRET = 99\n", encoding="utf-8")
        source = sample_python_file.read_text(encoding="utf-8")
        source = source.replace("return 1", "return 2")
        sample_python_file.write_text(source, encoding="utf-8")

        guard2 = GuardFile(temp_project)
        resolved, conflicted = guard2.resolve()
        assert len(resolved) == 2
        paths = {(e.path, e.identifier) for e in resolved}
        assert ("config.py", None) in paths
        assert ("sample.py", "simple_function") in paths


class TestResolveBlocksOnSourceConflicts:
    """Resolve fails when guarded source files have conflict markers."""

    def test_source_conflict_blocks_resolve(self, temp_project):
        """Resolve fails when a guarded source file has conflict markers."""
        filepath = temp_project / "config.py"
        conflicted_source = (
            "<<<<<<< HEAD\n"
            "SECRET = 42\n"
            "=======\n"
            "SECRET = 99\n"
            ">>>>>>> other-branch\n"
        )
        filepath.write_text(conflicted_source, encoding="utf-8")

        # .ai-guard has identifier entries for this file
        content = "config.py:SECRET:aaaa111122223333\n"
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        resolved, conflicted = guard.resolve()
        assert conflicted == ["config.py"]
        assert resolved == []

    def test_source_conflict_lists_all_files(self, temp_project):
        """Multiple conflicted source files are all listed."""
        for name in ["a.py", "b.py"]:
            filepath = temp_project / name
            filepath.write_text(
                f"<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n",
                encoding="utf-8",
            )

        content = "a.py:x:aaaa111122223333\nb.py:x:bbbb444455556666\n"
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        resolved, conflicted = guard.resolve()
        assert sorted(conflicted) == ["a.py", "b.py"]

    def test_file_level_entries_not_checked_for_markers(self, temp_project):
        """File-level (not identifier) entries don't trigger the source conflict check."""
        filepath = temp_project / "config.py"
        conflicted_source = (
            "<<<<<<< HEAD\n"
            "SECRET = 42\n"
            "=======\n"
            "SECRET = 99\n"
            ">>>>>>> other-branch\n"
        )
        filepath.write_text(conflicted_source, encoding="utf-8")

        # Only a file-level entry, no identifier entries
        content = "config.py:aaaa111122223333\n"
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        guard = GuardFile(temp_project)
        resolved, conflicted = guard.resolve()
        # No identifiers to check, so no conflict blocking
        assert conflicted == []
        assert len(resolved) == 1


class TestResolveCli:
    """Tests for the 'resolve' CLI command."""

    def test_resolve_cli_success(self, temp_project, monkeypatch):
        """'ai-guard resolve' succeeds with stale hashes."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        filepath.write_text("SECRET = 99\n", encoding="utf-8")
        result = main(["resolve"])
        assert result == 0

    def test_resolve_cli_blocks_on_source_conflicts(self, temp_project, monkeypatch, capsys):
        """'ai-guard resolve' fails when source files have conflict markers."""
        filepath = temp_project / "config.py"
        filepath.write_text("<<<<<<< HEAD\nx=1\n=======\nx=2\n>>>>>>> b\n", encoding="utf-8")

        content = "config.py:x:aaaa111122223333\n"
        (temp_project / ".ai-guard").write_text(content, encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["resolve"])
        assert result == 1
        captured = capsys.readouterr()
        assert "config.py" in captured.err
