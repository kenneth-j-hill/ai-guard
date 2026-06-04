"""Base parser interface for extracting identifiers from source code.

To add support for a new language, subclass Parser and implement the
extract_identifier() and list_identifiers() methods.
"""

import fnmatch
import importlib.util
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
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

    def expand_identifier_pattern(self, source: str, pattern: str) -> list[Identifier]:
        """Expand an identifier pattern to matching identifiers.

        This method handles wildcards and language-specific nested identifier
        syntax (e.g., Class.method in Python). Subclasses can override this
        to support language-specific patterns.

        Args:
            source: The full source code of the file.
            pattern: The identifier pattern, possibly with wildcards.

        Returns:
            A list of matching Identifier objects.
        """
        all_identifiers = self.list_identifiers(source)

        if "*" in pattern or "?" in pattern:
            return [i for i in all_identifiers if fnmatch.fnmatch(i.name, pattern)]
        else:
            return [i for i in all_identifiers if i.name == pattern]

    def extract_identifiers(
        self, source: str, names: list[str]
    ) -> dict[str, Optional[Identifier]]:
        """Extract multiple identifiers from a single source string.

        Bulk callers (e.g., ai-guard verify processing many entries per file)
        use this to parse the source once and resolve many names against it.
        The default loops `extract_identifier` per name; subclasses with
        expensive parsing (tree-sitter, ast.parse) should override to parse
        the source a single time.

        Args:
            source: The full source code of the file.
            names: Identifier names to look up.

        Returns:
            Dict mapping each requested name to its Identifier (or None).
        """
        return {name: self.extract_identifier(source, name) for name in names}


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


_external_parsers_loaded: set[str] = set()


def read_external_extensions(start_dir: Path) -> list[str]:
    """Read file extensions from a .ai-guard_parsers file without loading modules.

    This is a lightweight alternative to load_external_parsers() that only
    reads the extension declarations. Used by parse_target() to recognize
    custom file extensions in target strings.

    Args:
        start_dir: Directory to start searching from.

    Returns:
        List of file extensions (e.g., ['.rule', '.go']).
    """
    parsers_file = _find_parsers_file(start_dir)
    if parsers_file is None:
        return []

    extensions: list[str] = []
    for raw_line in parsers_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 3:
            continue
        ext_str = parts[2]
        for ext in ext_str.split(","):
            ext = ext.strip()
            if ext:
                extensions.append(ext)
    return extensions


def _find_parsers_file(start_dir: Path) -> Optional[Path]:
    """Walk up from start_dir looking for .ai-guard_parsers.

    Args:
        start_dir: Directory to start searching from.

    Returns:
        Path to the .ai-guard_parsers file, or None if not found.
    """
    current = start_dir.resolve()
    while True:
        candidate = current / ".ai-guard_parsers"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_external_parsers(start_dir: Path) -> list[str]:
    """Load parsers from a .ai-guard_parsers file found in an ancestor directory.

    The file format is one parser per line:
        path:ClassName:extensions

    Where:
        - path is the Python file containing the parser class (absolute,
          ~-relative, or relative to the directory containing .ai-guard_parsers)
        - ClassName is the Parser subclass to load
        - extensions is a comma-separated list of file extensions (e.g. .java,.jar)

    Lines starting with # and blank lines are ignored.

    Args:
        start_dir: Directory to start searching from.

    Returns:
        List of error messages (empty if all parsers loaded successfully).
    """
    parsers_file = _find_parsers_file(start_dir)
    if parsers_file is None:
        return []

    parsers_file_str = str(parsers_file)
    if parsers_file_str in _external_parsers_loaded:
        return []
    _external_parsers_loaded.add(parsers_file_str)

    base_dir = parsers_file.parent
    errors: list[str] = []

    for lineno, raw_line in enumerate(
        parsers_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(":")
        if len(parts) != 3:
            errors.append(
                f"{parsers_file}:{lineno}: expected 'path:ClassName:extensions', got: {line}"
            )
            continue

        module_path_str, class_name, ext_str = parts
        extensions = [e.strip() for e in ext_str.split(",") if e.strip()]
        if not extensions:
            errors.append(f"{parsers_file}:{lineno}: no extensions specified")
            continue

        # Resolve the module path
        module_path = Path(module_path_str).expanduser()
        if not module_path.is_absolute():
            module_path = (base_dir / module_path).resolve()

        if not module_path.is_file():
            errors.append(f"{parsers_file}:{lineno}: file not found: {module_path}")
            continue

        # Load the module
        module_name = f"_ai_guard_ext_{module_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                errors.append(f"{parsers_file}:{lineno}: cannot load module: {module_path}")
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            errors.append(f"{parsers_file}:{lineno}: error loading {module_path}: {e}")
            continue

        # Get the parser class
        parser_class = getattr(module, class_name, None)
        if parser_class is None:
            errors.append(
                f"{parsers_file}:{lineno}: class '{class_name}' not found in {module_path}"
            )
            continue

        if not (isinstance(parser_class, type) and issubclass(parser_class, Parser)):
            errors.append(
                f"{parsers_file}:{lineno}: {class_name} is not a Parser subclass"
            )
            continue

        register_parser(extensions, parser_class)

    return errors


def get_parser_for_file(filepath: str) -> Optional[Parser]:
    """Get the appropriate parser for a file based on its extension.

    On first call for a given .ai-guard_parsers file, loads any external
    parsers defined there.

    Args:
        filepath: Path to the file.

    Returns:
        A parser instance if one is registered for the file extension,
        None otherwise.
    """
    file_path = Path(filepath)
    ext = file_path.suffix.lower()

    # Try built-in parsers first
    parser_class = _PARSER_REGISTRY.get(ext)
    if parser_class:
        return parser_class()

    # Try loading external parsers from .ai-guard_parsers
    start_dir = file_path.parent if file_path.parent.is_dir() else Path.cwd()
    load_external_parsers(start_dir)

    # Check again after loading externals
    parser_class = _PARSER_REGISTRY.get(ext)
    if parser_class:
        return parser_class()

    return None
