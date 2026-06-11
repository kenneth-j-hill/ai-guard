"""Tests for the batch extract_identifiers API and verify()/resolve() reuse.

The batch API is what lets ai-guard parse a file once for N guarded
identifiers instead of N times. These tests pin both correctness (same
results as per-name extract_identifier) and the call-count contract that
delivers the perf win.
"""

import pytest
from pathlib import Path

from ai_guard.core import GuardFile, compute_identifier_hashes
from ai_guard.parsers import base as _base
from ai_guard.parsers.base import Parser, Identifier
from ai_guard.parsers.python import PythonParser

try:
    from ai_guard.parsers.rust import RustParser
    import ai_guard.parsers.rust as _rust
    _RUST_AVAILABLE = _rust._TREE_SITTER_AVAILABLE
except ImportError:
    _RUST_AVAILABLE = False


SAMPLE_PY = '''\
def alpha():
    return 1


def beta():
    return 2


def gamma():
    return 3


class Holder:
    def method_a(self):
        return "a"

    def method_b(self):
        return "b"
'''


SAMPLE_RS = '''\
pub fn alpha() -> i32 { 1 }

pub fn beta() -> i32 { 2 }

pub fn gamma() -> i32 { 3 }

pub struct Holder {
    pub x: i32,
    pub y: i32,
}

impl Holder {
    pub fn method_a(&self) -> i32 { self.x }
    pub fn method_b(&self) -> i32 { self.y }
}
'''


class TestBatchExtractCorrectness:
    """extract_identifiers must return results equivalent to per-name extract_identifier."""

    def test_python_batch_matches_individual(self):
        names = ["alpha", "beta", "gamma", "Holder", "Holder.method_a", "missing"]
        p = PythonParser()
        individual = {n: p.extract_identifier(SAMPLE_PY, n) for n in names}
        batch = p.extract_identifiers(SAMPLE_PY, names)
        for n in names:
            assert (batch[n].source if batch[n] else None) == (
                individual[n].source if individual[n] else None
            )

    @pytest.mark.skipif(not _RUST_AVAILABLE, reason="tree-sitter-rust not installed")
    def test_rust_batch_matches_individual(self):
        names = [
            "alpha", "beta", "gamma", "Holder",
            "Holder::method_a", "Holder::method_b", "Holder::x", "missing",
        ]
        p = RustParser()
        individual = {n: p.extract_identifier(SAMPLE_RS, n) for n in names}
        batch = p.extract_identifiers(SAMPLE_RS, names)
        for n in names:
            assert (batch[n].source if batch[n] else None) == (
                individual[n].source if individual[n] else None
            )

    def test_base_default_loops(self):
        """Parsers that don't override extract_identifiers still work via the default."""
        calls = []

        class Minimal(Parser):
            def extract_identifier(self, source, name):
                calls.append(name)
                return Identifier(name=name, source=name, start_line=1, end_line=1)

            def list_identifiers(self, source):
                return []

        result = Minimal().extract_identifiers("source", ["a", "b", "c"])
        assert list(result) == ["a", "b", "c"]
        assert calls == ["a", "b", "c"]


class TestParserInvokedOncePerFile:
    """verify() and resolve() must parse each file at most once regardless of entry count."""

    @pytest.mark.skipif(not _RUST_AVAILABLE, reason="tree-sitter-rust not installed")
    def test_verify_parses_rust_file_once(self, monkeypatch, tmp_path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        rs_path = tmp_path / "lib.rs"
        rs_path.write_text(SAMPLE_RS, encoding="utf-8")

        guard = GuardFile(tmp_path)
        guard.add_identifier("lib.rs", "alpha")
        guard.add_identifier("lib.rs", "beta")
        guard.add_identifier("lib.rs", "gamma")
        guard.add_identifier("lib.rs", "Holder::method_a")
        guard.add_identifier("lib.rs", "Holder::method_b")
        guard.save()

        parse_count = {"n": 0}
        original_make_parser = _rust._make_parser

        def counting_make_parser():
            parse_count["n"] += 1
            return original_make_parser()

        monkeypatch.setattr(_rust, "_make_parser", counting_make_parser)

        guard2 = GuardFile(tmp_path)
        assert guard2.verify() == []
        assert parse_count["n"] == 1, (
            f"verify() parsed lib.rs {parse_count['n']} times; expected exactly 1"
        )

    def test_verify_parses_python_file_once(self, monkeypatch, tmp_path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        py_path = tmp_path / "mod.py"
        py_path.write_text(SAMPLE_PY, encoding="utf-8")

        guard = GuardFile(tmp_path)
        for name in ["alpha", "beta", "gamma", "Holder.method_a", "Holder.method_b"]:
            guard.add_identifier("mod.py", name)
        guard.save()

        import ast
        parse_count = {"n": 0}
        original_parse = ast.parse

        def counting_parse(*args, **kwargs):
            parse_count["n"] += 1
            return original_parse(*args, **kwargs)

        monkeypatch.setattr(ast, "parse", counting_parse)

        guard2 = GuardFile(tmp_path)
        assert guard2.verify() == []
        assert parse_count["n"] == 1, (
            f"verify() parsed mod.py {parse_count['n']} times; expected exactly 1"
        )

    @pytest.mark.skipif(not _RUST_AVAILABLE, reason="tree-sitter-rust not installed")
    def test_update_all_parses_rust_file_once(self, monkeypatch, tmp_path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        rs_path = tmp_path / "lib.rs"
        rs_path.write_text(SAMPLE_RS, encoding="utf-8")

        guard = GuardFile(tmp_path)
        guard.add_identifier("lib.rs", "alpha")
        guard.add_identifier("lib.rs", "beta")
        guard.add_identifier("lib.rs", "gamma")
        guard.add_identifier("lib.rs", "Holder::method_a")
        guard.add_identifier("lib.rs", "Holder::method_b")
        guard.save()

        parse_count = {"n": 0}
        original_make_parser = _rust._make_parser

        def counting_make_parser():
            parse_count["n"] += 1
            return original_make_parser()

        monkeypatch.setattr(_rust, "_make_parser", counting_make_parser)

        guard2 = GuardFile(tmp_path)
        result = guard2.update_all(prune=False)
        assert result.errors == []
        assert parse_count["n"] == 1, (
            f"update_all() parsed lib.rs {parse_count['n']} times; expected exactly 1"
        )


class TestUpdateAll:
    """Batched update_all() semantics — must match the old per-entry loop."""

    def _guard_with(self, tmp_path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        (tmp_path / "mod.py").write_text(SAMPLE_PY, encoding="utf-8")
        guard = GuardFile(tmp_path)
        for name in ["alpha", "beta", "Holder.method_a"]:
            guard.add_identifier("mod.py", name)
        guard.save()
        return guard

    def test_unchanged_source_reports_no_updates(self, tmp_path):
        guard = self._guard_with(tmp_path)
        guard2 = GuardFile(tmp_path)
        result = guard2.update_all()
        assert result.updated == []
        assert result.unchanged_count == 3
        assert result.errors == []
        assert result.pruned == []

    def test_modified_identifier_is_reported_updated(self, tmp_path):
        guard = self._guard_with(tmp_path)
        # Change alpha's body; its stored hash should now differ.
        src = (tmp_path / "mod.py").read_text(encoding="utf-8")
        src = src.replace("def alpha():\n    return 1", "def alpha():\n    return 999")
        (tmp_path / "mod.py").write_text(src, encoding="utf-8")

        guard2 = GuardFile(tmp_path)
        result = guard2.update_all()
        updated_names = {e.identifier for e in result.updated}
        assert updated_names == {"alpha"}
        assert result.unchanged_count == 2

    def test_missing_identifier_errors_without_prune(self, tmp_path):
        guard = self._guard_with(tmp_path)
        # Remove beta from the source entirely.
        src = (tmp_path / "mod.py").read_text(encoding="utf-8")
        src = src.replace("def beta():\n    return 2\n", "")
        (tmp_path / "mod.py").write_text(src, encoding="utf-8")

        guard2 = GuardFile(tmp_path)
        result = guard2.update_all(prune=False)
        error_targets = {e.identifier for e, _ in result.errors}
        assert "beta" in error_targets
        # Stale entry is kept when not pruning.
        assert any(e.identifier == "beta" for e in guard2.entries)

    def test_missing_identifier_pruned_with_prune(self, tmp_path):
        guard = self._guard_with(tmp_path)
        src = (tmp_path / "mod.py").read_text(encoding="utf-8")
        src = src.replace("def beta():\n    return 2\n", "")
        (tmp_path / "mod.py").write_text(src, encoding="utf-8")

        guard2 = GuardFile(tmp_path)
        result = guard2.update_all(prune=True)
        pruned_targets = {e.identifier for e, _ in result.pruned}
        assert "beta" in pruned_targets
        # Entry is gone after pruning.
        assert not any(e.identifier == "beta" for e in guard2.entries)
        # Survivors remain.
        assert any(e.identifier == "alpha" for e in guard2.entries)

    def test_missing_file_pruned_with_prune(self, tmp_path):
        guard = self._guard_with(tmp_path)
        (tmp_path / "mod.py").unlink()

        guard2 = GuardFile(tmp_path)
        result = guard2.update_all(prune=True)
        reasons = {reason for _, reason in result.pruned}
        assert "file not found" in reasons
        # Only self-protection remains.
        assert all(e.is_self_protection for e in guard2.entries)


class TestComputeIdentifierHashes:
    """The bulk helper used by verify()/resolve()."""

    def test_returns_hash_for_present_and_none_for_missing(self, tmp_path):
        py_path = tmp_path / "mod.py"
        py_path.write_text(SAMPLE_PY, encoding="utf-8")

        result = compute_identifier_hashes(py_path, ["alpha", "missing", "beta"])
        assert result["alpha"] is not None
        assert result["beta"] is not None
        assert result["missing"] is None

    def test_dedupes_repeated_names(self, tmp_path):
        py_path = tmp_path / "mod.py"
        py_path.write_text(SAMPLE_PY, encoding="utf-8")

        result = compute_identifier_hashes(py_path, ["alpha", "alpha", "alpha"])
        assert list(result) == ["alpha"]

    def test_unknown_extension_returns_all_none(self, tmp_path):
        unknown = tmp_path / "data.weird"
        unknown.write_text("anything", encoding="utf-8")
        result = compute_identifier_hashes(unknown, ["a", "b"])
        assert result == {"a": None, "b": None}
