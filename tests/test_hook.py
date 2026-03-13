"""Tests for the git hooks installation and behavior."""

import shutil
import subprocess
import sys
import stat

import pytest

from ai_guard.cli import main, _PRE_COMMIT_SECTION, _POST_MERGE_SECTION, _MERGE_DRIVER_SCRIPT


IS_WINDOWS = sys.platform == "win32"


@pytest.fixture
def git_temp_project(tmp_path):
    """Create a temp project with a real git repo (needed for git config)."""
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)],
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"],
                   cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, capture_output=True, check=True)
    return tmp_path


class TestInstallGitHooks:
    """Tests for the install-git-hooks command."""

    def test_creates_pre_commit_hook(self, git_temp_project, monkeypatch):
        """install-git-hooks creates the pre-commit hook when user approves."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        result = main(["install-git-hooks"])

        assert result == 0
        hook_path = git_temp_project / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists()
        content = hook_path.read_text(encoding="utf-8")
        assert "ai-guard verify" in content
        assert "# --- ai-guard pre-commit ---" in content
        assert "# --- end ai-guard ---" in content

    def test_creates_post_merge_hook(self, git_temp_project, monkeypatch):
        """install-git-hooks creates the post-merge hook when user approves."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        hook_path = git_temp_project / ".git" / "hooks" / "post-merge"
        assert hook_path.exists()
        content = hook_path.read_text(encoding="utf-8")
        assert "ai-guard resolve" in content
        assert "# --- ai-guard post-merge ---" in content

    def test_installs_merge_driver_script(self, git_temp_project, monkeypatch):
        """install-git-hooks creates the merge driver script."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        driver_path = git_temp_project / ".git" / "hooks" / "ai-guard-merge-driver"
        assert driver_path.exists()

    def test_creates_gitattributes(self, git_temp_project, monkeypatch):
        """install-git-hooks adds merge driver entry to .gitattributes."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        attr_path = git_temp_project / ".gitattributes"
        assert attr_path.exists()
        content = attr_path.read_text(encoding="utf-8")
        assert ".ai-guard merge=ai-guard" in content

    def test_appends_to_existing_gitattributes(self, git_temp_project, monkeypatch):
        """Merge driver entry is appended to existing .gitattributes."""
        attr_path = git_temp_project / ".gitattributes"
        attr_path.write_text("*.txt text\n", encoding="utf-8")

        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        content = attr_path.read_text(encoding="utf-8")
        assert "*.txt text" in content
        assert ".ai-guard merge=ai-guard" in content

    @pytest.mark.skipif(IS_WINDOWS, reason="Windows does not use Unix file permissions")
    def test_hooks_are_executable(self, git_temp_project, monkeypatch):
        """Installed hooks have executable permissions."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        for name in ["pre-commit", "post-merge", "ai-guard-merge-driver"]:
            hook_path = git_temp_project / ".git" / "hooks" / name
            mode = hook_path.stat().st_mode
            assert mode & stat.S_IXUSR

    def test_appends_to_existing_non_ai_guard_hook(self, git_temp_project, monkeypatch):
        """ai-guard section is appended to existing non-ai-guard hooks."""
        hook_path = git_temp_project / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho 'existing hook'\n", encoding="utf-8")

        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        content = hook_path.read_text(encoding="utf-8")
        assert "existing hook" in content
        assert "ai-guard verify" in content

    def test_no_git_fails(self, tmp_path, monkeypatch):
        """install-git-hooks fails when not in a git repository."""
        monkeypatch.chdir(tmp_path)
        result = main(["install-git-hooks"])
        assert result == 1

    def test_user_declines_all(self, temp_project, monkeypatch):
        """Declining all prompts results in no hooks installed."""
        monkeypatch.chdir(temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = main(["install-git-hooks"])

        assert result == 0
        assert not (temp_project / ".git" / "hooks" / "pre-commit").exists()
        assert not (temp_project / ".git" / "hooks" / "post-merge").exists()


class TestInstallGitHooksIdempotent:
    """Running install-git-hooks twice is idempotent."""

    def test_second_run_shows_up_to_date(self, git_temp_project, monkeypatch, capsys):
        """Running install-git-hooks twice shows 'already installed'."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        # Second run — hooks should be detected as up to date
        main(["install-git-hooks"])
        captured = capsys.readouterr()
        assert "already installed" in captured.out

    def test_pre_commit_not_duplicated(self, git_temp_project, monkeypatch):
        """Running twice doesn't duplicate the pre-commit section."""
        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])
        main(["install-git-hooks"])

        hook_path = git_temp_project / ".git" / "hooks" / "pre-commit"
        content = hook_path.read_text(encoding="utf-8")
        assert content.count("ai-guard verify") == 1


class TestMigrateOldHook:
    """Tests for migrating old install-hook output."""

    def test_detects_old_hook_format(self, git_temp_project, monkeypatch):
        """Old-style hook (no delimiters) is detected and replaced."""
        old_content = (
            "#!/bin/sh\n"
            "# ai-guard pre-commit hook\n"
            "# Prevents commits that modify protected code\n"
            "\n"
            "ai-guard verify\n"
            "if [ $? -ne 0 ]; then\n"
            '    echo ""\n'
            '    echo "Commit blocked: Protected code was modified."\n'
            "    echo \"If this change is intentional, run 'ai-guard update <path>' first.\"\n"
            "    exit 1\n"
            "fi\n"
        )
        hook_path = git_temp_project / ".git" / "hooks" / "pre-commit"
        hook_path.write_text(old_content, encoding="utf-8")

        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        content = hook_path.read_text(encoding="utf-8")
        assert "# --- ai-guard pre-commit ---" in content
        assert "# ai-guard pre-commit hook" not in content

    def test_old_hook_appended_to_existing(self, git_temp_project, monkeypatch):
        """Old-style hook appended to existing content is replaced cleanly."""
        old_content = (
            "#!/bin/sh\n"
            "echo 'other stuff'\n"
            "\n"
            "# ai-guard pre-commit hook\n"
            "# Prevents commits that modify protected code\n"
            "\n"
            "ai-guard verify\n"
            "if [ $? -ne 0 ]; then\n"
            '    echo ""\n'
            '    echo "Commit blocked: Protected code was modified."\n'
            "    echo \"If this change is intentional, run 'ai-guard update <path>' first.\"\n"
            "    exit 1\n"
            "fi\n"
        )
        hook_path = git_temp_project / ".git" / "hooks" / "pre-commit"
        hook_path.write_text(old_content, encoding="utf-8")

        monkeypatch.chdir(git_temp_project)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        main(["install-git-hooks"])

        content = hook_path.read_text(encoding="utf-8")
        assert "other stuff" in content
        assert "# --- ai-guard pre-commit ---" in content
        assert content.count("ai-guard verify") == 1


class TestHookBehavior:
    """Tests documenting how the hooks behave."""

    def test_hook_blocks_on_protected_change(self, temp_project, monkeypatch):
        """The pre-commit hook blocks commits when protected code has changed."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        filepath.write_text("SECRET = 99\n", encoding="utf-8")
        result = main(["verify"])
        assert result == 1

    def test_hook_allows_unprotected_changes(self, temp_project, monkeypatch):
        """The pre-commit hook allows commits that don't touch protected code."""
        config = temp_project / "config.py"
        config.write_text("SECRET = 42\n", encoding="utf-8")
        other = temp_project / "other.py"
        other.write_text("x = 1\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        other.write_text("x = 2\n", encoding="utf-8")
        result = main(["verify"])
        assert result == 0

    def test_hook_allows_after_update(self, temp_project, monkeypatch):
        """After 'ai-guard update', verify passes."""
        filepath = temp_project / "config.py"
        filepath.write_text("SECRET = 42\n", encoding="utf-8")

        monkeypatch.chdir(temp_project)
        main(["add", "config.py"])

        filepath.write_text("SECRET = 99\n", encoding="utf-8")
        main(["update", "config.py"])

        result = main(["verify"])
        assert result == 0
