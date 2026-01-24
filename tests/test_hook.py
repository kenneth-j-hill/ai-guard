"""Tests for the git pre-commit hook.

These tests document the hook installation and behavior.
"""

import pytest
from pathlib import Path
import stat

from ai_guard.cli import main


class TestHookInstallation:
    """Tests for installing the pre-commit hook."""

    def test_install_hook_creates_file(self, temp_project, monkeypatch):
        """'ai-guard install-hook' creates the pre-commit hook."""
        monkeypatch.chdir(temp_project)
        result = main(["install-hook"])

        assert result == 0
        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists()

    def test_hook_is_executable(self, temp_project, monkeypatch):
        """The installed hook has executable permissions."""
        monkeypatch.chdir(temp_project)
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR  # Owner execute

    def test_hook_contains_verify_command(self, temp_project, monkeypatch):
        """The hook calls 'ai-guard verify'."""
        monkeypatch.chdir(temp_project)
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        content = hook_path.read_text()

        assert "ai-guard verify" in content

    def test_hook_exits_on_failure(self, temp_project, monkeypatch):
        """The hook script exits with non-zero on verification failure."""
        monkeypatch.chdir(temp_project)
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        content = hook_path.read_text()

        # Should check the exit code and exit 1 on failure
        assert "exit 1" in content

    def test_install_hook_appends_to_existing(self, temp_project, monkeypatch):
        """Installing hook appends to existing pre-commit hook."""
        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho 'existing hook'\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        result = main(["install-hook"])

        assert result == 0
        content = hook_path.read_text()
        assert "existing hook" in content
        assert "ai-guard verify" in content

    def test_install_hook_idempotent(self, temp_project, monkeypatch):
        """Installing hook twice doesn't duplicate the ai-guard section."""
        monkeypatch.chdir(temp_project)
        main(["install-hook"])
        main(["install-hook"])

        hook_path = temp_project / ".git" / "hooks" / "pre-commit"
        content = hook_path.read_text()

        # Should only appear once
        assert content.count("ai-guard verify") == 1

    def test_install_hook_no_git_fails(self, tmp_path, monkeypatch):
        """Installing hook fails when not in a git repository."""
        monkeypatch.chdir(tmp_path)
        result = main(["install-hook"])

        assert result == 1


class TestHookBehavior:
    """Tests documenting how the hook behaves during commits.

    Note: These are documentation tests - actual git commit testing
    would require integration tests with real git operations.
    """

    def test_hook_blocks_on_protected_change(self, temp_project, monkeypatch):
        """The hook blocks commits when protected code has changed.

        When a developer modifies protected code and tries to commit:
        1. Git runs the pre-commit hook
        2. The hook runs 'ai-guard verify'
        3. Verification fails due to hash mismatch
        4. Hook exits with code 1, blocking the commit
        5. Developer sees message about running 'ai-guard update'
        """
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])
        main(["install-hook"])

        # Simulate what happens when the file is modified
        filepath.write_text("SECRET = 99\n", encoding="utf-8")

        # The hook would run verify, which fails
        result = main(["verify"])
        assert result == 1  # Commit would be blocked

    def test_hook_allows_unprotected_changes(self, temp_project, monkeypatch):
        """The hook allows commits that don't touch protected code.

        When a developer modifies non-protected code:
        1. Git runs the pre-commit hook
        2. The hook runs 'ai-guard verify'
        3. Verification passes (no protected code changed)
        4. Hook exits with code 0, allowing the commit
        """
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")

        other = temp_project / "other.py"
        other.write_text("x = 1\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])  # Only protect config.py
        main(["install-hook"])

        # Modify the unprotected file
        other.write_text("x = 2\n", encoding="utf-8")

        # Verify still passes
        result = main(["verify"])
        assert result == 0  # Commit would proceed

    def test_hook_allows_after_update(self, temp_project, monkeypatch):
        """After running 'ai-guard update', commits are allowed.

        When a developer intentionally modifies protected code:
        1. Modify the protected code
        2. Run 'ai-guard update path/to/file.py'
        3. Hash is recalculated
        4. 'ai-guard verify' passes
        5. Commit proceeds
        """
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        # Intentionally modify
        filepath.write_text("SECRET = 99\n", encoding="utf-8")

        # Update the hash
        main(["update", "config.py"])

        # Now verify passes
        result = main(["verify"])
        assert result == 0  # Commit would proceed
