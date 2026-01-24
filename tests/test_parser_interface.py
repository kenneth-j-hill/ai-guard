"""Tests for the pluggable parser interface.

These tests document the parser abstraction and how to add
support for new languages.
"""

import pytest
from pathlib import Path
from typing import Optional

from ai_guard.parsers.base import (
    Parser,
    Identifier,
    register_parser,
    get_parser_for_file,
)
from ai_guard.parsers.python import PythonParser


class TestParserInterface:
    """Tests for the abstract Parser interface."""

    def test_parser_is_abstract(self):
        """Parser cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Parser()

    def test_parser_requires_extract_identifier(self):
        """Subclasses must implement extract_identifier."""

        class IncompleteParser(Parser):
            def list_identifiers(self, source: str) -> list[Identifier]:
                return []

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_parser_requires_list_identifiers(self):
        """Subclasses must implement list_identifiers."""

        class IncompleteParser(Parser):
            def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
                return None

        with pytest.raises(TypeError):
            IncompleteParser()


class TestParserRegistry:
    """Tests for the parser registration system."""

    def test_python_parser_registered(self):
        """PythonParser is registered for .py files."""
        parser = get_parser_for_file("test.py")
        assert parser is not None
        assert isinstance(parser, PythonParser)

    def test_pyw_files_use_python_parser(self):
        """PythonParser is also used for .pyw files."""
        parser = get_parser_for_file("script.pyw")
        assert isinstance(parser, PythonParser)

    def test_unknown_extension_returns_none(self):
        """Unknown file extensions return None."""
        parser = get_parser_for_file("file.unknown")
        assert parser is None

    def test_register_custom_parser(self):
        """Custom parsers can be registered for new extensions."""

        class CustomParser(Parser):
            def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
                return None

            def list_identifiers(self, source: str) -> list[Identifier]:
                return []

        register_parser([".custom"], CustomParser)

        parser = get_parser_for_file("file.custom")
        assert isinstance(parser, CustomParser)


class TestPythonParser:
    """Tests for the Python parser implementation."""

    def test_extract_function(self):
        """Can extract a function by name."""
        source = '''
def my_function():
    """Docstring."""
    return 42
'''
        parser = PythonParser()
        ident = parser.extract_identifier(source, "my_function")

        assert ident is not None
        assert ident.name == "my_function"
        assert "def my_function" in ident.source
        assert "return 42" in ident.source

    def test_extract_class(self):
        """Can extract a class by name."""
        source = '''
class MyClass:
    """A class."""

    def method(self):
        pass
'''
        parser = PythonParser()
        ident = parser.extract_identifier(source, "MyClass")

        assert ident is not None
        assert ident.name == "MyClass"
        assert "class MyClass" in ident.source
        assert "def method" in ident.source

    def test_extract_variable(self):
        """Can extract a module-level variable."""
        source = "MY_CONSTANT = 42\n"

        parser = PythonParser()
        ident = parser.extract_identifier(source, "MY_CONSTANT")

        assert ident is not None
        assert ident.name == "MY_CONSTANT"
        assert "42" in ident.source

    def test_extract_nonexistent_returns_none(self):
        """Returns None for nonexistent identifiers."""
        source = "x = 1\n"

        parser = PythonParser()
        ident = parser.extract_identifier(source, "nonexistent")

        assert ident is None

    def test_list_identifiers(self):
        """Can list all top-level identifiers."""
        source = '''
CONSTANT = 1

def func():
    pass

class Cls:
    pass
'''
        parser = PythonParser()
        identifiers = parser.list_identifiers(source)

        names = {i.name for i in identifiers}
        assert names == {"CONSTANT", "func", "Cls"}

    def test_syntax_error_returns_empty(self):
        """Syntax errors return empty results instead of crashing."""
        source = "def broken(:\n"

        parser = PythonParser()

        ident = parser.extract_identifier(source, "broken")
        assert ident is None

        identifiers = parser.list_identifiers(source)
        assert identifiers == []

    def test_identifier_includes_line_numbers(self):
        """Extracted identifiers include line number information."""
        source = '''# Comment
# Another comment

def my_function():
    pass
'''
        parser = PythonParser()
        ident = parser.extract_identifier(source, "my_function")

        assert ident is not None
        assert ident.start_line == 4
        assert ident.end_line == 5


class TestAddingNewLanguageSupport:
    """Documentation tests showing how to add a new language.

    To add support for a new language (e.g., JavaScript):

    1. Create a new parser class that extends Parser
    2. Implement extract_identifier() and list_identifiers()
    3. Register the parser for appropriate file extensions

    Example:

        # ai_guard/parsers/javascript.py

        class JavaScriptParser(Parser):
            def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
                # Use a JS parser like esprima or tree-sitter
                tree = parse_javascript(source)
                for node in walk(tree):
                    if is_identifier(node) and node.name == name:
                        return Identifier(
                            name=node.name,
                            source=extract_source(source, node),
                            start_line=node.start_line,
                            end_line=node.end_line,
                        )
                return None

            def list_identifiers(self, source: str) -> list[Identifier]:
                # Return all functions, classes, and const declarations
                ...

        # Register for JS and TS files
        register_parser(['.js', '.jsx', '.ts', '.tsx'], JavaScriptParser)
    """

    def test_custom_parser_example(self):
        """A minimal example of a custom parser."""

        class SimpleParser(Parser):
            """A simple parser that treats each line starting with 'def ' as a function."""

            def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
                lines = source.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith(f"def {name}"):
                        return Identifier(
                            name=name,
                            source=line,
                            start_line=i + 1,
                            end_line=i + 1,
                        )
                return None

            def list_identifiers(self, source: str) -> list[Identifier]:
                identifiers = []
                lines = source.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("def "):
                        name = line.split("(")[0].replace("def ", "")
                        identifiers.append(
                            Identifier(
                                name=name,
                                source=line,
                                start_line=i + 1,
                                end_line=i + 1,
                            )
                        )
                return identifiers

        parser = SimpleParser()
        source = "def foo():\ndef bar():\n"

        assert parser.extract_identifier(source, "foo") is not None
        assert parser.extract_identifier(source, "baz") is None
        assert len(parser.list_identifiers(source)) == 2
