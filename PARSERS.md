# Custom Parsers

AI-Guard supports external parsers for languages not included in the built-in set. This lets you add identifier-level protection for any language without modifying ai-guard itself.

## How It Works

Create a `.ai-guard_parsers` file in your project root (or any ancestor directory). AI-Guard walks up from the file being parsed until it finds one.

This means you can place `.ai-guard_parsers` in:
- A project root for project-specific parsers
- Your home directory (`~/.ai-guard_parsers`) for parsers that apply everywhere

## File Format

Each line specifies a parser module:

```
path:ClassName:extensions
```

- **path** — path to the Python file containing the parser class. Can be absolute, `~`-relative, or relative to the directory containing `.ai-guard_parsers`.
- **ClassName** — name of the `Parser` subclass in that file.
- **extensions** — comma-separated list of file extensions to handle (include the dot).

Blank lines and lines starting with `#` are ignored.

### Example

```
# .ai-guard_parsers
./parsers/java_parser.py:JavaParser:.java
~/custom-parsers/kotlin_parser.py:KotlinParser:.kt,.kts
/opt/parsers/go_parser.py:GoParser:.go
```

## Writing a Parser

A parser must subclass `ai_guard.parsers.base.Parser` and implement two methods:

```python
from ai_guard.parsers.base import Parser, Identifier
from typing import Optional


class JavaParser(Parser):
    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        """Extract a single identifier by name from source code.

        Args:
            source: Full source code of the file.
            name: Identifier name to find (e.g., "calculateTax").

        Returns:
            An Identifier if found, None otherwise.
        """
        # Parse source and locate the identifier
        ...

    def list_identifiers(self, source: str) -> list[Identifier]:
        """List all top-level identifiers in the source code.

        Args:
            source: Full source code of the file.

        Returns:
            List of all identifiers found.
        """
        # Return all functions, classes, interfaces, etc.
        ...
```

### The Identifier Object

Each identifier has:

| Field | Type | Description |
|---|---|---|
| `name` | `str` | The identifier name (e.g., `"calculateTax"`) |
| `source` | `str` | The full source text of the identifier (this gets hashed) |
| `start_line` | `int` | Starting line number (1-based) |
| `end_line` | `int` | Ending line number (inclusive) |

The `source` field is what ai-guard hashes. Include everything that defines the identifier: signature, body, decorators/annotations, docstrings. Changes to any of these should trigger a protection violation.

### Optional: Nested Identifiers

If your language has nested identifiers (like Java's `ClassName.method`), override `expand_identifier_pattern()`:

```python
def expand_identifier_pattern(self, source: str, pattern: str) -> list[Identifier]:
    """Handle patterns like ClassName.method or ClassName.*"""
    if "." in pattern and "*" not in pattern.split(".")[0]:
        # Language-specific nested identifier logic
        ...
    return super().expand_identifier_pattern(source, pattern)
```

The default implementation handles wildcards (`*`, `?`) via fnmatch on the flat identifier list.

## Precedence

External parsers do **not** override built-in parsers. If ai-guard already handles an extension (`.py`, `.c`, `.rs`, etc.), the built-in parser is used regardless of what `.ai-guard_parsers` says. This prevents accidental breakage.

## Troubleshooting

Errors during parser loading are printed to stderr but don't halt execution. Common issues:

- **File not found** — check that the path is correct relative to the `.ai-guard_parsers` file's directory
- **Class not found** — verify the class name matches exactly (case-sensitive)
- **Not a Parser subclass** — your class must inherit from `ai_guard.parsers.base.Parser`
- **Import errors** — if your parser has dependencies (like tree-sitter), make sure they're installed

## Example: Minimal Go Parser

```python
# go_parser.py
import re
from ai_guard.parsers.base import Parser, Identifier
from typing import Optional


class GoParser(Parser):
    _FUNC_RE = re.compile(
        r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(', re.MULTILINE
    )

    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        for ident in self.list_identifiers(source):
            if ident.name == name:
                return ident
        return None

    def list_identifiers(self, source: str) -> list[Identifier]:
        lines = source.split('\n')
        identifiers = []
        for match in self._FUNC_RE.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            # Find the closing brace (simplified)
            brace_count = 0
            end_line = start_line
            for i, line in enumerate(lines[start_line - 1:], start=start_line):
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and '{' in ''.join(lines[start_line - 1:i]):
                    end_line = i
                    break
            func_source = '\n'.join(lines[start_line - 1:end_line])
            identifiers.append(Identifier(name, func_source, start_line, end_line))
        return identifiers
```

Then in `.ai-guard_parsers`:
```
./go_parser.py:GoParser:.go
```

And use it:
```bash
ai-guard add main.go:handleRequest
```
