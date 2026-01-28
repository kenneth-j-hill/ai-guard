"""C/C++ parser using GCC.

This parser extracts function and struct/class definitions from C/C++ source
files by using GCC to preprocess and validate the code, combined with regex
parsing for identifier extraction.
"""

import fnmatch
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ai_guard.parsers.base import Parser, Identifier, register_parser


class GCCParserBase(Parser):
    """Base parser for C/C++ using GCC.

    This parser:
    1. Uses regex to find identifier boundaries
    2. Can optionally validate syntax with GCC

    Subclasses set the compiler command (gcc vs g++).
    """

    COMPILER = "gcc"  # Override in subclass
    LANGUAGE = "c"    # Override in subclass

    # Pattern for function definitions
    FUNCTION_PATTERN = re.compile(
        r"""
        ^[ \t]*                     # Start of line, optional indent
        (?P<attrs>(?:__\w+__\s*\([^)]*\)\s*)*)  # Optional GCC attributes
        (?P<modifiers>(?:static|inline|extern|virtual|const|unsigned|signed|long|short)\s+)*
        (?P<return_type>[\w_][\w_\s\*&:<>,]*?)  # Return type
        \s+
        (?P<name>[\w_]+)            # Function name
        \s*
        (?P<params>\([^)]*\))       # Parameters
        \s*
        (?:const\s*)?               # Optional const
        (?:override\s*)?            # Optional override (C++)
        (?:noexcept(?:\([^)]*\))?\s*)?  # Optional noexcept
        \s*
        \{                          # Opening brace
        """,
        re.MULTILINE | re.VERBOSE
    )

    # Pattern for struct/class definitions
    STRUCT_CLASS_PATTERN = re.compile(
        r"""
        ^[ \t]*                     # Start of line
        (?P<keyword>struct|class|union|enum)  # Keyword
        \s+
        (?P<name>[\w_]+)            # Name
        \s*
        (?::\s*[^{]+)?              # Optional inheritance (C++)
        \s*
        \{                          # Opening brace
        """,
        re.MULTILINE | re.VERBOSE
    )

    # Pattern for typedef
    TYPEDEF_PATTERN = re.compile(
        r"""
        ^[ \t]*                     # Start of line
        typedef\s+
        (?P<definition>.+?)         # The type definition
        \s+
        (?P<name>[\w_]+)            # The new type name
        \s*;
        """,
        re.MULTILINE | re.VERBOSE
    )

    # Pattern for #define macros
    DEFINE_PATTERN = re.compile(
        r"""
        ^[ \t]*                     # Start of line
        \#\s*define\s+              # #define
        (?P<name>[\w_]+)            # Macro name
        (?P<params>\([^)]*\))?      # Optional macro parameters
        (?P<body>.*)                # Body (may continue with \)
        """,
        re.MULTILINE | re.VERBOSE
    )

    # Pattern for global variables
    GLOBAL_VAR_PATTERN = re.compile(
        r"""
        ^[ \t]*                     # Start of line
        (?:static\s+|extern\s+|const\s+|volatile\s+)*  # Modifiers
        (?P<type>[\w_][\w_\s\*&]+?) # Type
        \s+
        (?P<name>[\w_]+)            # Variable name
        \s*
        (?:\[[^\]]*\])?             # Optional array brackets
        \s*
        (?:=\s*[^;]+)?              # Optional initializer
        \s*;
        """,
        re.MULTILINE | re.VERBOSE
    )

    def check_syntax(self, source: str) -> bool:
        """Check if the source has valid syntax using GCC.

        Args:
            source: The source code to check.

        Returns:
            True if syntax is valid, False otherwise.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{self.LANGUAGE}", delete=False
        ) as f:
            f.write(source)
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                [self.COMPILER, "-fsyntax-only", "-x", self.LANGUAGE, temp_path],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def list_identifiers(self, source: str) -> list[Identifier]:
        """List all top-level identifiers in C/C++ source code."""
        identifiers = []
        lines = source.split("\n")
        seen_names = set()

        # Find functions
        for match in self.FUNCTION_PATTERN.finditer(source):
            name = match.group("name")
            if name in seen_names:
                continue
            # Skip control flow keywords
            if name in ("if", "while", "for", "switch", "return", "sizeof"):
                continue
            ident = self._find_function(source, lines, name)
            if ident:
                identifiers.append(ident)
                seen_names.add(name)

        # Find structs/classes
        for match in self.STRUCT_CLASS_PATTERN.finditer(source):
            name = match.group("name")
            if name in seen_names:
                continue
            ident = self._find_struct_class(source, lines, name)
            if ident:
                identifiers.append(ident)
                seen_names.add(name)

        # Find typedefs
        for match in self.TYPEDEF_PATTERN.finditer(source):
            name = match.group("name")
            if name in seen_names:
                continue
            ident = self._find_typedef(source, lines, name)
            if ident:
                identifiers.append(ident)
                seen_names.add(name)

        # Find macros
        for match in self.DEFINE_PATTERN.finditer(source):
            name = match.group("name")
            if name in seen_names:
                continue
            ident = self._find_macro(source, lines, name)
            if ident:
                identifiers.append(ident)
                seen_names.add(name)

        return identifiers

    def _find_function(
        self, source: str, lines: list[str], name: str
    ) -> Optional[Identifier]:
        """Find a function definition by name."""
        # Build pattern for this specific function
        # The tricky part is handling "char *func" vs "char* func" vs "char * func"
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?:(?:__\w+__\s*\([^)]*\)\s*)*)
            (?:(?:static|inline|extern|virtual|const|unsigned|signed|long|short)\s+)*
            [\w_][\w_\s\*&:<>,]*?
            [\s\*&]
            {re.escape(name)}
            \s*
            \([^)]*\)
            \s*
            (?:const\s*)?
            (?:override\s*)?
            (?:noexcept(?:\([^)]*\))?\s*)?
            \s*
            \{{
            """,
            re.MULTILINE | re.VERBOSE
        )

        match = pattern.search(source)
        if not match:
            return None

        start_pos = match.start()
        start_line = source[:start_pos].count("\n") + 1

        # Find matching closing brace
        brace_pos = match.end() - 1
        end_pos = self._find_matching_brace(source, brace_pos)
        if end_pos == -1:
            return None

        end_line = source[:end_pos + 1].count("\n") + 1
        identifier_source = "\n".join(lines[start_line - 1 : end_line])

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_struct_class(
        self, source: str, lines: list[str], name: str
    ) -> Optional[Identifier]:
        """Find a struct/class/union/enum definition by name."""
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?P<keyword>struct|class|union|enum)
            \s+
            {re.escape(name)}
            \s*
            (?::\s*[^{{]+)?
            \s*
            \{{
            """,
            re.MULTILINE | re.VERBOSE
        )

        match = pattern.search(source)
        if not match:
            return None

        start_pos = match.start()
        start_line = source[:start_pos].count("\n") + 1

        # Find matching closing brace
        brace_pos = match.end() - 1
        end_pos = self._find_matching_brace(source, brace_pos)
        if end_pos == -1:
            return None

        # Include trailing semicolon if present
        remaining = source[end_pos + 1 : end_pos + 10].lstrip()
        if remaining.startswith(";"):
            end_pos = source.index(";", end_pos) + 1

        end_line = source[:end_pos].count("\n") + 1
        identifier_source = "\n".join(lines[start_line - 1 : end_line])

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_typedef(
        self, source: str, lines: list[str], name: str
    ) -> Optional[Identifier]:
        """Find a typedef by name."""
        # Simple typedef (no struct)
        pattern = re.compile(
            rf"^[ \t]*typedef\s+.+?\s+{re.escape(name)}\s*;",
            re.MULTILINE
        )

        match = pattern.search(source)
        if not match:
            return None

        start_pos = match.start()
        end_pos = match.end()
        start_line = source[:start_pos].count("\n") + 1
        end_line = source[:end_pos].count("\n") + 1

        identifier_source = "\n".join(lines[start_line - 1 : end_line])

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_macro(
        self, source: str, lines: list[str], name: str
    ) -> Optional[Identifier]:
        """Find a #define macro by name."""
        pattern = re.compile(
            rf"^[ \t]*#\s*define\s+{re.escape(name)}(?:\([^)]*\))?",
            re.MULTILINE
        )

        match = pattern.search(source)
        if not match:
            return None

        start_pos = match.start()
        start_line = source[:start_pos].count("\n") + 1

        # Handle line continuations
        end_line = start_line
        while end_line <= len(lines) and lines[end_line - 1].rstrip().endswith("\\"):
            end_line += 1

        identifier_source = "\n".join(lines[start_line - 1 : end_line])

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_global_var(
        self, source: str, lines: list[str], name: str
    ) -> Optional[Identifier]:
        """Find a global variable by name."""
        # Handle "char *name" vs "char* name" vs "char * name"
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?:static\s+|extern\s+|const\s+|volatile\s+)*
            [\w_][\w_\s\*&]+?
            [\s\*&]
            {re.escape(name)}
            \s*
            (?:\[[^\]]*\])?
            \s*
            (?:=\s*[^;]+)?
            \s*;
            """,
            re.MULTILINE | re.VERBOSE
        )

        match = pattern.search(source)
        if not match:
            return None

        start_pos = match.start()
        end_pos = match.end()
        start_line = source[:start_pos].count("\n") + 1
        end_line = source[:end_pos].count("\n") + 1

        identifier_source = "\n".join(lines[start_line - 1 : end_line])

        return Identifier(
            name=name,
            source=identifier_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_matching_brace(self, source: str, open_pos: int) -> int:
        """Find the position of the matching closing brace."""
        if open_pos >= len(source) or source[open_pos] != "{":
            return -1

        depth = 1
        pos = open_pos + 1
        in_string = False
        in_char = False
        in_block_comment = False
        in_line_comment = False

        while pos < len(source) and depth > 0:
            char = source[pos]
            prev_char = source[pos - 1] if pos > 0 else ""
            next_char = source[pos + 1] if pos + 1 < len(source) else ""

            # Handle line comments
            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                pos += 1
                continue

            # Handle block comments
            if in_block_comment:
                if char == "/" and prev_char == "*":
                    in_block_comment = False
                pos += 1
                continue

            # Start of comments
            if not in_string and not in_char:
                if char == "/" and next_char == "/":
                    in_line_comment = True
                    pos += 2
                    continue
                if char == "/" and next_char == "*":
                    in_block_comment = True
                    pos += 2
                    continue

            # Handle strings
            if char == '"' and prev_char != "\\" and not in_char:
                in_string = not in_string
                pos += 1
                continue

            # Handle char literals
            if char == "'" and prev_char != "\\" and not in_string:
                in_char = not in_char
                pos += 1
                continue

            # Count braces (only outside strings/chars/comments)
            if not in_string and not in_char:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1

            pos += 1

        return pos - 1 if depth == 0 else -1

    def expand_identifier_pattern(self, source: str, pattern: str) -> list[Identifier]:
        """Expand an identifier pattern to matching identifiers.

        Supports C/C++ scope resolution operator for struct/class members:
        - "MyStruct::field" - specific struct/class member
        - "MyClass::*" - all members of a struct/class
        - "MyClass::get_*" - members matching a pattern

        Args:
            source: The full source code of the file.
            pattern: The identifier pattern, possibly with wildcards or :: notation.

        Returns:
            A list of matching Identifier objects.
        """
        # Check for C/C++ scope resolution operator
        if "::" in pattern:
            parts = pattern.split("::", 1)
            struct_name, member_pattern = parts

            # Get all members of the struct/class
            all_members = self.list_struct_members(source, struct_name)

            # Filter by member pattern (which may include wildcards)
            if "*" in member_pattern or "?" in member_pattern:
                full_pattern = f"{struct_name}::{member_pattern}"
                return [m for m in all_members if fnmatch.fnmatch(m.name, full_pattern)]
            else:
                return [m for m in all_members if m.name == pattern]

        # Fall back to base implementation for top-level identifiers
        return super().expand_identifier_pattern(source, pattern)

    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        """Extract a specific identifier from C/C++ source code."""
        lines = source.split("\n")

        # Check for struct/class member notation
        if "::" in name:
            return self._extract_struct_member(source, lines, name)

        # Try each pattern type
        for finder in [
            self._find_function,
            self._find_struct_class,
            self._find_typedef,
            self._find_macro,
            self._find_global_var,
        ]:
            identifier = finder(source, lines, name)
            if identifier:
                return identifier

        return None

    def _extract_struct_member(
        self, source: str, lines: list[str], qualified_name: str
    ) -> Optional[Identifier]:
        """Extract a struct/class member using :: notation.

        Args:
            source: The full source code.
            lines: Source code split into lines.
            qualified_name: Name in format "StructName::member_name".

        Returns:
            An Identifier if found, None otherwise.
        """
        parts = qualified_name.split("::", 1)
        if len(parts) != 2:
            return None
        struct_name, member_name = parts

        # Find the struct/class
        struct_ident = self._find_struct_class(source, lines, struct_name)
        if not struct_ident:
            return None

        # Parse members within the struct body
        struct_source = struct_ident.source
        struct_lines = struct_source.split("\n")

        # Find the member within the struct
        member = self._find_member_in_struct(struct_source, struct_lines, member_name, qualified_name)
        return member

    def _find_member_in_struct(
        self, struct_source: str, struct_lines: list[str], member_name: str, qualified_name: str
    ) -> Optional[Identifier]:
        """Find a specific member within a struct/class body.

        Args:
            struct_source: The source code of the struct/class.
            struct_lines: Source lines of the struct.
            member_name: The member name to find.
            qualified_name: The full qualified name (StructName::member).

        Returns:
            An Identifier if found, None otherwise.
        """
        # Find the opening brace
        brace_idx = struct_source.find("{")
        if brace_idx == -1:
            return None

        # Get content between braces (excluding the struct declaration line and closing)
        body_start = brace_idx + 1
        body_end = struct_source.rfind("}")
        if body_end == -1:
            body_end = len(struct_source)
        body = struct_source[body_start:body_end]

        # Try to find member as a function
        func_ident = self._find_member_function(body, member_name, qualified_name)
        if func_ident:
            return func_ident

        # Try to find member as a field
        field_ident = self._find_member_field(body, member_name, qualified_name)
        if field_ident:
            return field_ident

        return None

    def _find_member_function(
        self, body: str, member_name: str, qualified_name: str
    ) -> Optional[Identifier]:
        """Find a member function within a struct/class body."""
        # Pattern for member function
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?:(?:static|inline|virtual|const|explicit)\s+)*
            [\w_][\w_\s\*&:<>,]*?
            [\s\*&]?
            {re.escape(member_name)}
            \s*
            \([^)]*\)
            \s*
            (?:const\s*)?
            (?:override\s*)?
            (?:noexcept(?:\([^)]*\))?\s*)?
            \s*
            \{{
            """,
            re.MULTILINE | re.VERBOSE
        )

        match = pattern.search(body)
        if not match:
            return None

        start_pos = match.start()
        brace_pos = match.end() - 1
        end_pos = self._find_matching_brace(body, brace_pos)
        if end_pos == -1:
            return None

        member_source = body[start_pos:end_pos + 1].strip()
        start_line = body[:start_pos].count("\n") + 1
        end_line = body[:end_pos + 1].count("\n") + 1

        return Identifier(
            name=qualified_name,
            source=member_source,
            start_line=start_line,
            end_line=end_line,
        )

    def _find_member_field(
        self, body: str, member_name: str, qualified_name: str
    ) -> Optional[Identifier]:
        """Find a member field (variable) within a struct/class body."""
        # Pattern for member field
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?:(?:static|const|volatile|mutable)\s+)*
            [\w_][\w_\s\*&:<>,]*?
            [\s\*&]
            {re.escape(member_name)}
            \s*
            (?:\[[^\]]*\])?           # Optional array brackets
            \s*
            (?:=\s*[^;]+)?            # Optional initializer
            \s*;
            """,
            re.MULTILINE | re.VERBOSE
        )

        match = pattern.search(body)
        if not match:
            return None

        member_source = match.group(0).strip()
        start_pos = match.start()
        end_pos = match.end()
        start_line = body[:start_pos].count("\n") + 1
        end_line = body[:end_pos].count("\n") + 1

        return Identifier(
            name=qualified_name,
            source=member_source,
            start_line=start_line,
            end_line=end_line,
        )

    def list_struct_members(self, source: str, struct_name: str) -> list[Identifier]:
        """List all members of a specific struct/class.

        Args:
            source: The full source code of the file.
            struct_name: Name of the struct/class to list members for.

        Returns:
            A list of all identifiers (methods, fields) in the struct/class.
            Names are qualified with the struct name (e.g., "StructName::field").
        """
        lines = source.split("\n")
        identifiers = []

        # Find the struct/class
        struct_ident = self._find_struct_class(source, lines, struct_name)
        if not struct_ident:
            return []

        struct_source = struct_ident.source

        # Find the opening brace
        brace_idx = struct_source.find("{")
        if brace_idx == -1:
            return []

        # Get content between braces
        body_start = brace_idx + 1
        body_end = struct_source.rfind("}")
        if body_end == -1:
            body_end = len(struct_source)
        body = struct_source[body_start:body_end]

        # Find all member functions
        for match in self._iter_member_functions(body):
            name = match.group("name")
            qualified_name = f"{struct_name}::{name}"
            member = self._find_member_function(body, name, qualified_name)
            if member:
                identifiers.append(member)

        # Find all member fields
        for match in self._iter_member_fields(body):
            name = match.group("name")
            qualified_name = f"{struct_name}::{name}"
            # Avoid duplicates (in case pattern matches function names too)
            if not any(i.name == qualified_name for i in identifiers):
                member = self._find_member_field(body, name, qualified_name)
                if member:
                    identifiers.append(member)

        return identifiers

    def _iter_member_functions(self, body: str):
        """Iterate over member function matches in a struct body."""
        pattern = re.compile(
            r"""
            ^[ \t]*
            (?:(?:static|inline|virtual|const|explicit)\s+)*
            [\w_][\w_\s\*&:<>,]*?
            [\s\*&]?
            (?P<name>[\w_]+)
            \s*
            \([^)]*\)
            \s*
            (?:const\s*)?
            (?:override\s*)?
            (?:noexcept(?:\([^)]*\))?\s*)?
            \s*
            \{
            """,
            re.MULTILINE | re.VERBOSE
        )
        seen = set()
        for match in pattern.finditer(body):
            name = match.group("name")
            # Skip control flow keywords
            if name in ("if", "while", "for", "switch", "return", "sizeof"):
                continue
            if name not in seen:
                seen.add(name)
                yield match

    def _iter_member_fields(self, body: str):
        """Iterate over member field matches in a struct body."""
        pattern = re.compile(
            r"""
            ^[ \t]*
            (?:(?:static|const|volatile|mutable)\s+)*
            [\w_][\w_\s\*&:<>,]*?
            [\s\*&]
            (?P<name>[\w_]+)
            \s*
            (?:\[[^\]]*\])?
            \s*
            (?:=\s*[^;]+)?
            \s*;
            """,
            re.MULTILINE | re.VERBOSE
        )
        seen = set()
        for match in pattern.finditer(body):
            name = match.group("name")
            if name not in seen:
                seen.add(name)
                yield match


class GCCParser(GCCParserBase):
    """Parser for C code using GCC."""

    COMPILER = "gcc"
    LANGUAGE = "c"


class GPPParser(GCCParserBase):
    """Parser for C++ code using G++."""

    COMPILER = "g++"
    LANGUAGE = "c++"


# Register parsers for file extensions
register_parser([".c", ".h"], GCCParser)
register_parser([".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".C", ".H"], GPPParser)
