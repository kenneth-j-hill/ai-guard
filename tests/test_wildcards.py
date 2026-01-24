"""Tests for wildcard pattern matching.

These tests document how wildcard patterns work when protecting
multiple identifiers at once.
"""

import pytest
from pathlib import Path

from ai_guard.core import GuardFile


class TestWildcardPatterns:
    """Tests for wildcard pattern matching in identifiers."""

    def test_asterisk_matches_multiple(self, temp_project, sample_python_file):
        """The * wildcard matches multiple identifiers."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "test_invariant_*")

        # Should match test_invariant_one, test_invariant_two, test_invariant_three
        assert len(entries) == 3
        names = {e.identifier for e in entries}
        assert names == {"test_invariant_one", "test_invariant_two", "test_invariant_three"}

    def test_each_match_gets_own_hash(self, temp_project, sample_python_file):
        """Each matched identifier gets its own hash."""
        guard = GuardFile(temp_project)
        entries = guard.add_identifier("sample.py", "test_invariant_*")

        # Each should have a different hash (they have different content)
        hashes = {e.hash for e in entries}
        assert len(hashes) == 3

    def test_wildcard_no_matches_raises(self, temp_project, sample_python_file):
        """A wildcard pattern that matches nothing raises an error."""
        guard = GuardFile(temp_project)

        with pytest.raises(ValueError, match="No identifiers matching"):
            guard.add_identifier("sample.py", "nonexistent_*")

    def test_question_mark_wildcard(self, temp_project):
        """The ? wildcard matches a single character."""
        source = '''
def func_a():
    pass

def func_b():
    pass

def func_ab():
    pass
'''
        filepath = temp_project / "funcs.py"
        filepath.write_text(source, encoding="utf-8")

        guard = GuardFile(temp_project)
        entries = guard.add_identifier("funcs.py", "func_?")

        # Should match func_a and func_b, but not func_ab
        assert len(entries) == 2
        names = {e.identifier for e in entries}
        assert names == {"func_a", "func_b"}

    def test_wildcard_entries_saved_individually(self, temp_project, sample_python_file):
        """Wildcard matches are saved as individual entries in .ai-guard."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "test_invariant_*")
        guard.save()

        # Read the file directly
        content = (temp_project / ".ai-guard").read_text()
        lines = [l for l in content.strip().split("\n") if l]

        assert len(lines) == 3
        assert all("test_invariant_" in line for line in lines)

    def test_wildcard_verify_detects_single_change(self, temp_project, sample_python_file):
        """Verification detects when just one of the wildcard matches changed."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "test_invariant_*")
        guard.save()

        # Modify just one function
        content = sample_python_file.read_text()
        content = content.replace(
            "def test_invariant_two():",
            "def test_invariant_two(modified):"
        )
        sample_python_file.write_text(content)

        failures = guard.verify()
        assert len(failures) == 1
        assert failures[0][0].identifier == "test_invariant_two"

    def test_update_with_wildcard(self, temp_project, sample_python_file):
        """Updating with a wildcard updates all matching entries."""
        guard = GuardFile(temp_project)
        guard.add_identifier("sample.py", "test_invariant_*")
        original_hashes = {e.identifier: e.hash for e in guard.entries}
        guard.save()

        # Modify all functions
        content = sample_python_file.read_text()
        content = content.replace("assert True", "assert 1 == 1")
        sample_python_file.write_text(content)

        # Update with wildcard
        guard.update("sample.py", "test_invariant_*")
        new_hashes = {e.identifier: e.hash for e in guard.entries}

        # All hashes should have changed
        for name in original_hashes:
            assert original_hashes[name] != new_hashes[name]

        # Verify should pass now
        assert guard.verify() == []
