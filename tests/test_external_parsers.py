"""Tests for external parser loading via .ai-guard_parsers files."""

import pytest
from pathlib import Path
from typing import Optional

from ai_guard.parsers.base import (
    Parser,
    Identifier,
    _find_parsers_file,
    load_external_parsers,
    read_external_extensions,
    get_parser_for_file,
    _PARSER_REGISTRY,
    _external_parsers_loaded,
)


# Minimal parser module content for test fixtures
_GOOD_PARSER_MODULE = '''\
from ai_guard.parsers.base import Parser, Identifier
from typing import Optional


class TestLangParser(Parser):
    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        for ident in self.list_identifiers(source):
            if ident.name == name:
                return ident
        return None

    def list_identifiers(self, source: str) -> list[Identifier]:
        return [Identifier("dummy", source, 1, 1)]
'''

_BAD_PARSER_MODULE = '''\
class NotAParser:
    pass
'''


class TestFindParsersFile:
    """Tests for ancestor directory traversal."""

    def test_finds_in_current_dir(self, tmp_path: Path):
        """Finds .ai-guard_parsers in the start directory."""
        parsers_file = tmp_path / ".ai-guard_parsers"
        parsers_file.write_text("# empty\n")

        result = _find_parsers_file(tmp_path)
        assert result == parsers_file

    def test_finds_in_parent_dir(self, tmp_path: Path):
        """Walks up to find .ai-guard_parsers in a parent directory."""
        parsers_file = tmp_path / ".ai-guard_parsers"
        parsers_file.write_text("# empty\n")
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)

        result = _find_parsers_file(child)
        assert result == parsers_file

    def test_returns_none_when_not_found(self, tmp_path: Path):
        """Returns None when no .ai-guard_parsers exists."""
        child = tmp_path / "sub"
        child.mkdir()

        result = _find_parsers_file(child)
        assert result is None

    def test_stops_at_nearest_ancestor(self, tmp_path: Path):
        """Uses the nearest .ai-guard_parsers, not a higher one."""
        root_file = tmp_path / ".ai-guard_parsers"
        root_file.write_text("# root\n")
        child = tmp_path / "project"
        child.mkdir()
        child_file = child / ".ai-guard_parsers"
        child_file.write_text("# project\n")

        result = _find_parsers_file(child)
        assert result == child_file


class TestLoadExternalParsers:
    """Tests for loading parsers from .ai-guard_parsers files."""

    def setup_method(self):
        """Clear external parser state between tests."""
        _external_parsers_loaded.clear()

    def test_loads_valid_parser(self, tmp_path: Path):
        """Loads a parser module and registers it."""
        # Write the parser module
        parser_file = tmp_path / "my_parser.py"
        parser_file.write_text(_GOOD_PARSER_MODULE)

        # Write the config
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./my_parser.py:TestLangParser:.xyz\n")

        errors = load_external_parsers(tmp_path)
        assert errors == []
        assert ".xyz" in _PARSER_REGISTRY

        # Verify the parser works
        parser = _PARSER_REGISTRY[".xyz"]()
        idents = parser.list_identifiers("hello")
        assert len(idents) == 1

        # Cleanup
        del _PARSER_REGISTRY[".xyz"]

    def test_loads_multiple_extensions(self, tmp_path: Path):
        """A single parser can register for multiple extensions."""
        parser_file = tmp_path / "my_parser.py"
        parser_file.write_text(_GOOD_PARSER_MODULE)

        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./my_parser.py:TestLangParser:.abc,.def\n")

        errors = load_external_parsers(tmp_path)
        assert errors == []
        assert ".abc" in _PARSER_REGISTRY
        assert ".def" in _PARSER_REGISTRY

        # Cleanup
        del _PARSER_REGISTRY[".abc"]
        del _PARSER_REGISTRY[".def"]

    def test_skips_comments_and_blanks(self, tmp_path: Path):
        """Comments and blank lines are ignored."""
        parser_file = tmp_path / "my_parser.py"
        parser_file.write_text(_GOOD_PARSER_MODULE)

        config = tmp_path / ".ai-guard_parsers"
        config.write_text("# This is a comment\n\n./my_parser.py:TestLangParser:.commenttest\n")

        errors = load_external_parsers(tmp_path)
        assert errors == []
        assert ".commenttest" in _PARSER_REGISTRY

        # Cleanup
        del _PARSER_REGISTRY[".commenttest"]

    def test_error_on_malformed_line(self, tmp_path: Path):
        """Reports error for lines that don't have 3 colon-separated parts."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("bad line\n")

        errors = load_external_parsers(tmp_path)
        assert len(errors) == 1
        assert "expected" in errors[0]

    def test_error_on_missing_file(self, tmp_path: Path):
        """Reports error when the parser module doesn't exist."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./nonexistent.py:Foo:.bar\n")

        errors = load_external_parsers(tmp_path)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_error_on_missing_class(self, tmp_path: Path):
        """Reports error when the class doesn't exist in the module."""
        parser_file = tmp_path / "my_parser.py"
        parser_file.write_text(_GOOD_PARSER_MODULE)

        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./my_parser.py:NonexistentClass:.bar\n")

        errors = load_external_parsers(tmp_path)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_error_on_non_parser_class(self, tmp_path: Path):
        """Reports error when the class isn't a Parser subclass."""
        parser_file = tmp_path / "bad_parser.py"
        parser_file.write_text(_BAD_PARSER_MODULE)

        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./bad_parser.py:NotAParser:.bar\n")

        errors = load_external_parsers(tmp_path)
        assert len(errors) == 1
        assert "not a Parser subclass" in errors[0]

    def test_loads_only_once(self, tmp_path: Path):
        """Same .ai-guard_parsers file is not loaded twice."""
        parser_file = tmp_path / "my_parser.py"
        parser_file.write_text(_GOOD_PARSER_MODULE)

        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./my_parser.py:TestLangParser:.oncetest\n")

        errors1 = load_external_parsers(tmp_path)
        assert errors1 == []

        # Remove from registry to check if second load re-adds it
        del _PARSER_REGISTRY[".oncetest"]

        errors2 = load_external_parsers(tmp_path)
        assert errors2 == []
        assert ".oncetest" not in _PARSER_REGISTRY  # Not re-loaded

    def test_no_parsers_file_returns_empty(self, tmp_path: Path):
        """Returns empty list when no .ai-guard_parsers exists."""
        errors = load_external_parsers(tmp_path)
        assert errors == []

    def test_tilde_path_expansion(self, tmp_path: Path):
        """Paths starting with ~ are expanded."""
        config = tmp_path / ".ai-guard_parsers"
        # Use a path that won't exist under home — should get "file not found"
        config.write_text("~/nonexistent_ai_guard_test_parser.py:Foo:.bar\n")

        errors = load_external_parsers(tmp_path)
        assert len(errors) == 1
        assert "not found" in errors[0]
        # Verify it expanded ~ (shouldn't contain literal ~)
        assert "~" not in errors[0]


class TestReadExternalExtensions:
    """Tests for reading extensions without loading modules."""

    def test_reads_extensions(self, tmp_path: Path):
        """Reads extensions from .ai-guard_parsers without loading modules."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./parser.py:MyParser:.rule\n")

        extensions = read_external_extensions(tmp_path)
        assert ".rule" in extensions

    def test_reads_multiple_extensions(self, tmp_path: Path):
        """Reads comma-separated extensions from a single line."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./parser.py:MyParser:.foo,.bar,.baz\n")

        extensions = read_external_extensions(tmp_path)
        assert extensions == [".foo", ".bar", ".baz"]

    def test_skips_comments_and_blanks(self, tmp_path: Path):
        """Comments and blank lines are ignored."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("# comment\n\n./parser.py:MyParser:.xyz\n")

        extensions = read_external_extensions(tmp_path)
        assert extensions == [".xyz"]

    def test_skips_malformed_lines(self, tmp_path: Path):
        """Malformed lines are silently skipped."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("bad line\n./parser.py:MyParser:.good\n")

        extensions = read_external_extensions(tmp_path)
        assert extensions == [".good"]

    def test_no_file_returns_empty(self, tmp_path: Path):
        """Returns empty list when no .ai-guard_parsers exists."""
        extensions = read_external_extensions(tmp_path)
        assert extensions == []


class TestParseTargetWithExternalExtensions:
    """Tests that parse_target recognizes custom extensions."""

    def setup_method(self):
        """Reset cached regex between tests."""
        import ai_guard.cli as cli_module
        cli_module._target_ext_re = None

    def test_custom_extension_splits_target(self, tmp_path: Path, monkeypatch):
        """parse_target splits file:identifier for custom extensions."""
        config = tmp_path / ".ai-guard_parsers"
        config.write_text("./parser.py:MyParser:.rule\n")
        monkeypatch.chdir(tmp_path)

        from ai_guard.cli import parse_target
        path, identifier = parse_target("sigil/rules/control.rule:easPacked")
        assert path == "sigil/rules/control.rule"
        assert identifier == "easPacked"

    def test_builtin_extensions_still_work(self, tmp_path: Path, monkeypatch):
        """Built-in extensions work even without .ai-guard_parsers."""
        monkeypatch.chdir(tmp_path)

        from ai_guard.cli import parse_target
        path, identifier = parse_target("src/auth.py:calculate_tax")
        assert path == "src/auth.py"
        assert identifier == "calculate_tax"

    def test_unknown_extension_no_split(self, tmp_path: Path, monkeypatch):
        """Unknown extensions without .ai-guard_parsers don't split."""
        monkeypatch.chdir(tmp_path)

        from ai_guard.cli import parse_target
        path, identifier = parse_target("file.unknown:something")
        assert path == "file.unknown:something"
        assert identifier is None
