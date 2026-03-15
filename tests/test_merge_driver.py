"""Tests for the merge driver logic."""

import pytest

from ai_guard.core import ProtectedEntry
from ai_guard.merge_driver import union_merge, parse_entries, run_merge_driver


class TestUnionMerge:
    """Tests for the union merge algorithm."""

    def test_same_entry_both_sides(self):
        """Identical entries are deduplicated."""
        entry = ProtectedEntry(path="config.py", identifier=None, hash="aaaa111122223333")
        result = union_merge([entry], [entry])
        assert len(result) == 1
        assert result[0].hash == "aaaa111122223333"

    def test_same_target_different_hashes(self):
        """Same target with different hashes keeps both."""
        ours = ProtectedEntry(path="config.py", identifier=None, hash="aaaa111122223333")
        theirs = ProtectedEntry(path="config.py", identifier=None, hash="bbbb444455556666")
        result = union_merge([ours], [theirs])
        assert len(result) == 2
        hashes = {e.hash for e in result}
        assert hashes == {"aaaa111122223333", "bbbb444455556666"}

    def test_new_entry_one_side(self):
        """Entry only on one side is included."""
        ours = ProtectedEntry(path="config.py", identifier=None, hash="aaaa111122223333")
        theirs = ProtectedEntry(path="other.py", identifier=None, hash="bbbb444455556666")
        result = union_merge([ours], [theirs])
        assert len(result) == 2
        paths = {e.path for e in result}
        assert paths == {"config.py", "other.py"}

    def test_disjoint_sets(self):
        """Completely disjoint entry sets produce a union."""
        ours = [
            ProtectedEntry(path="a.py", identifier=None, hash="aaaa111122223333"),
            ProtectedEntry(path="b.py", identifier=None, hash="bbbb444455556666"),
        ]
        theirs = [
            ProtectedEntry(path="c.py", identifier=None, hash="cccc777788889999"),
            ProtectedEntry(path="d.py", identifier=None, hash="dddd000011112222"),
        ]
        result = union_merge(ours, theirs)
        assert len(result) == 4
        paths = {e.path for e in result}
        assert paths == {"a.py", "b.py", "c.py", "d.py"}

    def test_empty_ours(self):
        """Empty ours with entries on theirs keeps theirs."""
        theirs = [ProtectedEntry(path="config.py", identifier=None, hash="aaaa111122223333")]
        result = union_merge([], theirs)
        assert len(result) == 1

    def test_empty_theirs(self):
        """Entries on ours with empty theirs keeps ours."""
        ours = [ProtectedEntry(path="config.py", identifier=None, hash="aaaa111122223333")]
        result = union_merge(ours, [])
        assert len(result) == 1

    def test_both_empty(self):
        """Both empty produces empty result."""
        result = union_merge([], [])
        assert result == []

    def test_identifier_entries(self):
        """Identifier-level entries are handled correctly."""
        ours = ProtectedEntry(path="a.py", identifier="func_a", hash="aaaa111122223333")
        theirs = ProtectedEntry(path="a.py", identifier="func_b", hash="bbbb444455556666")
        result = union_merge([ours], [theirs])
        assert len(result) == 2

    def test_preserves_order_ours_first(self):
        """Ours entries come before theirs entries."""
        ours = ProtectedEntry(path="a.py", identifier=None, hash="aaaa111122223333")
        theirs = ProtectedEntry(path="b.py", identifier=None, hash="bbbb444455556666")
        result = union_merge([ours], [theirs])
        assert result[0].path == "a.py"
        assert result[1].path == "b.py"

    def test_strips_self_protection_from_both_sides(self):
        """Self-protection entries with different hashes should not produce duplicates."""
        ours = [
            ProtectedEntry(path=".ai-guard", identifier=None, hash="aaaa111122223333"),
            ProtectedEntry(path="auth.py", identifier="login", hash="bbbb444455556666"),
        ]
        theirs = [
            ProtectedEntry(path=".ai-guard", identifier=None, hash="cccc777788889999"),
            ProtectedEntry(path="billing.py", identifier="charge", hash="dddd000011112222"),
        ]
        result = union_merge(ours, theirs)
        ai_guard_entries = [e for e in result if e.path == ".ai-guard"]
        assert len(ai_guard_entries) == 0, (
            f"Self-protection entries should be stripped, got {len(ai_guard_entries)}"
        )
        assert len(result) == 2
        paths = {e.path for e in result}
        assert paths == {"auth.py", "billing.py"}

    def test_strips_identical_self_protection(self):
        """Even identical self-protection entries are stripped."""
        ours = [
            ProtectedEntry(path=".ai-guard", identifier=None, hash="aaaa111122223333"),
            ProtectedEntry(path="config.py", identifier=None, hash="bbbb444455556666"),
        ]
        theirs = [
            ProtectedEntry(path=".ai-guard", identifier=None, hash="aaaa111122223333"),
            ProtectedEntry(path="config.py", identifier=None, hash="bbbb444455556666"),
        ]
        result = union_merge(ours, theirs)
        ai_guard_entries = [e for e in result if e.path == ".ai-guard"]
        assert len(ai_guard_entries) == 0
        assert len(result) == 1


class TestRunMergeDriver:
    """Tests for the full merge driver execution."""

    def test_writes_merged_result(self, tmp_path):
        """The merge driver writes the merged result to the ours file."""
        ancestor = tmp_path / "ancestor"
        ours = tmp_path / "ours"
        theirs = tmp_path / "theirs"

        ancestor.write_text("config.py:0000000000000000\n", encoding="utf-8")
        ours.write_text("config.py:aaaa111122223333\n", encoding="utf-8")
        theirs.write_text("config.py:bbbb444455556666\nother.py:cccc777788889999\n", encoding="utf-8")

        result = run_merge_driver(str(ancestor), str(ours), str(theirs))
        assert result == 0

        merged = parse_entries(ours)
        paths = {(e.path, e.hash) for e in merged}
        assert ("config.py", "aaaa111122223333") in paths
        assert ("config.py", "bbbb444455556666") in paths
        assert ("other.py", "cccc777788889999") in paths

    def test_always_returns_zero(self, tmp_path):
        """The merge driver always succeeds."""
        for name in ["ancestor", "ours", "theirs"]:
            (tmp_path / name).write_text("", encoding="utf-8")

        result = run_merge_driver(
            str(tmp_path / "ancestor"),
            str(tmp_path / "ours"),
            str(tmp_path / "theirs"),
        )
        assert result == 0
