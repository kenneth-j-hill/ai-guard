"""Base parser interface for extracting identifiers from source code.

To add support for a new language, subclass Parser and implement the
extract_identifier() and list_identifiers() methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Identifier:
    """Represents a code identifier (function, class, variable, etc.)."""

    name: str
    source: str  # The full source code of the identifier
    start_line: int
    end_line: int

    def __hash__(self) -> int:
        return hash((self.name, self.source))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Identifier):
            return NotImplemented
        return self.name == other.name and self.source == other.source


class Parser(ABC):
    """Abstract base class for language-specific parsers.

    To add support for a new language:

    1. Subclass Parser
    2. Implement extract_identifier() to get a specific identifier by name
    3. Implement list_identifiers() to get all identifiers in a file
    4. Register the parser in get_parser_for_file()

    Example for a hypothetical JavaScript parser:

        class JavaScriptParser(Parser):
            def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
                # Use a JS parser (e.g., esprima) to find the identifier
                ...

            def list_identifiers(self, source: str) -> list[Identifier]:
                # Return all functions, classes, and constants
                ...
    """

    @abstractmethod
    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        """Extract a specific identifier from source code.

        Args:
            source: The full source code of the file.
            name: The name of the identifier to extract.

        Returns:
            An Identifier object if found, None otherwise.
        """
        pass

    @abstractmethod
    def list_identifiers(self, source: str) -> list[Identifier]:
        """List all identifiers in the source code.

        Args:
            source: The full source code of the file.

        Returns:
            A list of all identifiers found in the source.
        """
        pass


# Registry of file extensions to parser classes
_PARSER_REGISTRY: dict[str, type[Parser]] = {}


def register_parser(extensions: list[str], parser_class: type[Parser]) -> None:
    """Register a parser for file extensions.

    Args:
        extensions: List of file extensions (e.g., ['.py', '.pyw']).
        parser_class: The parser class to use for these extensions.
    """
    for ext in extensions:
        _PARSER_REGISTRY[ext] = parser_class


def get_parser_for_file(filepath: str) -> Optional[Parser]:
    """Get the appropriate parser for a file based on its extension.

    Args:
        filepath: Path to the file.

    Returns:
        A parser instance if one is registered for the file extension,
        None otherwise.
    """
    from pathlib import Path
    ext = Path(filepath).suffix.lower()
    parser_class = _PARSER_REGISTRY.get(ext)
    if parser_class:
        return parser_class()
    return None
