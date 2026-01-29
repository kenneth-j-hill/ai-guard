"""Tests for the command-line interface.

These tests document the CLI commands and their behavior.
"""

import pytest
from pathlib import Path
import os

from ai_guard.cli import main, parse_target


class TestParseTarget:
    """Tests for parsing CLI target arguments."""

    def test_file_only(self):
        """A plain path is parsed as a file without identifier."""
        path, identifier = parse_target("src/config.py")
        assert path == "src/config.py"
        assert identifier is None

    def test_file_with_identifier(self):
        """path:identifier is parsed correctly."""
        path, identifier = parse_target("src/config.py:my_function")
        assert path == "src/config.py"
        assert identifier == "my_function"

    def test_file_with_wildcard_identifier(self):
        """Wildcard patterns in identifiers are preserved."""
        path, identifier = parse_target("src/test.py:test_*")
        assert path == "src/test.py"
        assert identifier == "test_*"

    def test_deep_path(self):
        """Deep paths are handled correctly."""
        path, identifier = parse_target("src/deep/nested/module.py:func")
        assert path == "src/deep/nested/module.py"
        assert identifier == "func"

    def test_glob_with_extension_and_identifier(self):
        """Glob pattern with extension and identifier is parsed correctly."""
        path, identifier = parse_target("tests/test_*.py:*")
        assert path == "tests/test_*.py"
        assert identifier == "*"

    def test_glob_without_extension(self):
        """Glob pattern without visible extension splits on last colon."""
        path, identifier = parse_target("tests/test_*:*")
        assert path == "tests/test_*"
        assert identifier == "*"

    def test_glob_with_specific_identifier(self):
        """Glob pattern with specific identifier pattern."""
        path, identifier = parse_target("src/*:my_func")
        assert path == "src/*"
        assert identifier == "my_func"

    def test_class_member_dotted_notation(self):
        """Class member with dot notation is parsed correctly."""
        path, identifier = parse_target("src/models.py:MyClass.method")
        assert path == "src/models.py"
        assert identifier == "MyClass.method"

    def test_class_member_wildcard(self):
        """Class member wildcard pattern is parsed correctly."""
        path, identifier = parse_target("src/models.py:MyClass.*")
        assert path == "src/models.py"
        assert identifier == "MyClass.*"

    def test_class_member_partial_wildcard(self):
        """Class member partial wildcard pattern is parsed correctly."""
        path, identifier = parse_target("src/models.py:MyClass.test_*")
        assert path == "src/models.py"
        assert identifier == "MyClass.test_*"


class TestAddCommand:
    """Tests for the 'add' command."""

    def test_add_file(self, temp_project, monkeypatch):
        """'ai-guard add file.py' protects the entire file."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["add", "config.py"])

        assert result == 0
        assert (temp_project / ".ai-guard").exists()

        content = (temp_project / ".ai-guard").read_text()
        assert "config.py:" in content
        assert "::" not in content  # No double colon means no identifier

    def test_add_identifier(self, temp_project, sample_python_file, monkeypatch):
        """'ai-guard add file.py:func' protects the identifier."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "sample.py:simple_function"])

        assert result == 0

        content = (temp_project / ".ai-guard").read_text()
        assert "sample.py:simple_function:" in content

    def test_add_wildcard(self, temp_project, sample_python_file, monkeypatch):
        """'ai-guard add file.py:pattern*' expands wildcards."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "sample.py:test_invariant_*"])

        assert result == 0

        content = (temp_project / ".ai-guard").read_text()
        assert "test_invariant_one" in content
        assert "test_invariant_two" in content
        assert "test_invariant_three" in content

    def test_add_nonexistent_file_fails(self, temp_project, monkeypatch):
        """Adding a nonexistent file returns an error."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "nonexistent.py"])

        assert result == 1

    def test_add_nonexistent_identifier_fails(self, temp_project, sample_python_file, monkeypatch):
        """Adding a nonexistent identifier returns an error."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "sample.py:nonexistent"])

        assert result == 1

    def test_add_class_member(self, temp_project, sample_python_file, monkeypatch):
        """'ai-guard add file.py:Class.method' protects a class member."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "sample.py:SimpleClass.method"])

        assert result == 0

        content = (temp_project / ".ai-guard").read_text()
        assert "sample.py:SimpleClass.method:" in content

    def test_add_class_member_wildcard(self, temp_project, sample_python_file, monkeypatch):
        """'ai-guard add file.py:Class.*' protects all class members."""
        monkeypatch.chdir(temp_project)
        result = main(["add", "sample.py:DecoratedClass.*"])

        assert result == 0

        content = (temp_project / ".ai-guard").read_text()
        assert "DecoratedClass.prop" in content
        assert "DecoratedClass.static_method" in content

    def test_add_multiple_targets(self, temp_project, monkeypatch):
        """'ai-guard add file1.py file2.py' protects multiple files."""
        file1 = temp_project / "config.py"
        file1.write_text("SECRET = 42\n", encoding="utf-8")
        file2 = temp_project / "settings.py"
        file2.write_text("DEBUG = True\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["add", "config.py", "settings.py"])

        assert result == 0
        content = (temp_project / ".ai-guard").read_text()
        assert "config.py" in content
        assert "settings.py" in content

    def test_add_glob_pattern(self, temp_project, monkeypatch):
        """'ai-guard add *.py' expands glob and protects matching files."""
        file1 = temp_project / "config.py"
        file1.write_text("SECRET = 42\n", encoding="utf-8")
        file2 = temp_project / "settings.py"
        file2.write_text("DEBUG = True\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["add", "*.py"])

        assert result == 0
        content = (temp_project / ".ai-guard").read_text()
        assert "config.py" in content
        assert "settings.py" in content

    def test_add_glob_with_identifier(self, temp_project, monkeypatch):
        """'ai-guard add *.py:func' protects identifier in all matching files."""
        file1 = temp_project / "module1.py"
        file1.write_text("def helper():\n    pass\n", encoding="utf-8")
        file2 = temp_project / "module2.py"
        file2.write_text("def helper():\n    return 1\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["add", "*.py:helper"])

        assert result == 0
        content = (temp_project / ".ai-guard").read_text()
        assert "module1.py:helper" in content
        assert "module2.py:helper" in content


class TestVerifyCommand:
    """Tests for the 'verify' command."""

    def test_verify_passes_unchanged(self, temp_project, monkeypatch):
        """'ai-guard verify' passes when nothing changed."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        result = main(["verify"])
        assert result == 0

    def test_verify_fails_on_change(self, temp_project, monkeypatch):
        """'ai-guard verify' fails when protected code changed."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        # Modify the file
        filepath.write_text("SECRET = 99\n", encoding="utf-8")

        result = main(["verify"])
        assert result == 1


class TestUpdateCommand:
    """Tests for the 'update' command."""

    def test_update_file(self, temp_project, monkeypatch):
        """'ai-guard update file.py' updates the hash."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        # Modify the file
        filepath.write_text("SECRET = 99\n", encoding="utf-8")

        # Verify fails
        assert main(["verify"]) == 1

        # Update
        result = main(["update", "config.py"])
        assert result == 0

        # Verify passes now
        assert main(["verify"]) == 0

    def test_update_all(self, temp_project, sample_python_file, monkeypatch):
        """'ai-guard update --all' updates all protected entries."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        main(["add", "sample.py:simple_function"])

        # Modify both
        config.write_text("SECRET = 99\n", encoding="utf-8")
        original = sample_python_file.read_text()
        sample_python_file.write_text(original.replace("return 1", "return 999"))

        # Verify fails
        assert main(["verify"]) == 1

        # Update all
        result = main(["update", "--all"])
        assert result == 0

        # Verify passes now
        assert main(["verify"]) == 0

    def test_update_all_unchanged(self, temp_project, monkeypatch, capsys):
        """'ai-guard update --all' only shows entries that changed."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        # Update without changing anything
        result = main(["update", "--all"])
        assert result == 0

        # Should not print "Updated" since nothing changed
        captured = capsys.readouterr()
        assert "Updated" not in captured.out

    def test_update_all_empty(self, temp_project, monkeypatch, capsys):
        """'ai-guard update --all' with no entries shows message."""
        monkeypatch.chdir(temp_project)
        result = main(["update", "--all"])

        assert result == 0
        captured = capsys.readouterr()
        assert "No protected entries" in captured.out

    def test_update_all_with_targets_fails(self, temp_project, monkeypatch, capsys):
        """'ai-guard update --all file.py' is invalid."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["update", "--all", "config.py"])

        assert result == 1
        captured = capsys.readouterr()
        assert "Cannot use --all with specific targets" in captured.err

    def test_update_no_args_fails(self, temp_project, monkeypatch, capsys):
        """'ai-guard update' without args or --all fails."""
        monkeypatch.chdir(temp_project)
        result = main(["update"])

        assert result == 1
        captured = capsys.readouterr()
        assert "Must specify targets or use --all" in captured.err


class TestRemoveCommand:
    """Tests for the 'remove' command."""

    def test_remove_file(self, temp_project, monkeypatch):
        """'ai-guard remove file.py' removes protection."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        assert (temp_project / ".ai-guard").exists()

        result = main(["remove", "config.py"])
        assert result == 0

        # File should be empty or have no entries
        content = (temp_project / ".ai-guard").read_text()
        assert "config.py" not in content

    def test_remove_nonexistent_fails(self, temp_project, monkeypatch):
        """Removing a non-protected file returns an error."""
        monkeypatch.chdir(temp_project)

        # Create empty guard file
        (temp_project / ".ai-guard").write_text("", encoding="utf-8")

        result = main(["remove", "nonexistent.py"])
        assert result == 1


class TestListCommand:
    """Tests for the 'list' command."""

    def test_list_empty(self, temp_project, monkeypatch, capsys):
        """'ai-guard list' shows message when no protections exist."""
        monkeypatch.chdir(temp_project)
        result = main(["list"])

        assert result == 0
        captured = capsys.readouterr()
        assert "No protected entries" in captured.out

    def test_list_entries(self, temp_project, sample_python_file, monkeypatch, capsys):
        """'ai-guard list' shows all protected entries."""
        monkeypatch.chdir(temp_project)
        main(["add", "sample.py"])
        main(["add", "sample.py:simple_function"])

        result = main(["list"])

        assert result == 0
        captured = capsys.readouterr()
        assert "sample.py" in captured.out
        assert "simple_function" in captured.out


class TestQuietOption:
    """Tests for the --quiet / -q flag."""

    def test_add_quiet_no_stdout(self, temp_project, monkeypatch, capsys):
        """'ai-guard -q add file.py' produces no stdout."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["-q", "add", "config.py"])

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_add_quiet_still_protects(self, temp_project, monkeypatch):
        """'-q add' still writes the .ai-guard file."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["-q", "add", "config.py"])

        assert (temp_project / ".ai-guard").exists()
        content = (temp_project / ".ai-guard").read_text()
        assert "config.py" in content

    def test_verify_quiet_success(self, temp_project, monkeypatch, capsys):
        """'-q verify' produces no stdout on success."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        capsys.readouterr()  # clear add output

        result = main(["-q", "verify"])

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_verify_quiet_failure_still_shows_stderr(self, temp_project, monkeypatch, capsys):
        """'-q verify' still prints errors to stderr on failure."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        filepath.write_text("SECRET = 99\n", encoding="utf-8")
        capsys.readouterr()  # clear add output

        result = main(["-q", "verify"])

        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "config.py" in captured.err

    def test_list_quiet(self, temp_project, sample_python_file, monkeypatch, capsys):
        """'-q list' suppresses list output."""
        monkeypatch.chdir(temp_project)
        main(["add", "sample.py"])
        capsys.readouterr()  # clear add output

        result = main(["-q", "list"])

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_verify_quiet_failure_shows_violation_details(self, temp_project, monkeypatch, capsys):
        """'-q verify' shows full violation details on stderr."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        filepath.write_text("SECRET = 99\n", encoding="utf-8")
        capsys.readouterr()  # clear add output

        result = main(["-q", "verify"])

        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "AI-Guard violations found:" in captured.err
        assert "config.py" in captured.err

    def test_add_quiet_error_still_shows_stderr(self, temp_project, monkeypatch, capsys):
        """'-q add nonexistent.py' still prints errors to stderr."""
        monkeypatch.chdir(temp_project)
        result = main(["-q", "add", "nonexistent.py"])

        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error" in captured.err
