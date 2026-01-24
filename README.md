# ai-guard

Protect code from incidental modifications by an AI.

## Installation

```bash
pip install ai-guard
```

Or install from source:

```bash
git clone https://github.com/your-username/ai-guard.git
cd ai-guard
pip install -e ".[dev]"
```

## Quick Start

```bash
# Protect an entire file
ai-guard add src/auth.py

# Protect a specific function
ai-guard add src/billing.py:calculate_tax

# Protect multiple functions with a wildcard
ai-guard add tests/test_core.py:test_invariant_*

# Install the git pre-commit hook
ai-guard install-hook
```

Now if anyone (human or AI) tries to commit changes to protected code, the commit will be blocked:

```
$ git commit -m "Quick fix"
Protection violations found:
  src/auth.py - hash mismatch

Commit blocked: Protected code was modified.
If this change is intentional, run 'ai-guard update <path>' first.
```

## Commands

### `ai-guard add <target>`

Add protection for a file or identifier.

```bash
# Whole file
ai-guard add path/to/file.py

# Specific identifier (function, class, variable)
ai-guard add path/to/file.py:my_function

# Wildcard pattern
ai-guard add path/to/file.py:test_*
```

### `ai-guard update <target>`

Update the hash after intentionally modifying protected code.

```bash
ai-guard update path/to/file.py
ai-guard update path/to/file.py:my_function
```

### `ai-guard remove <target>`

Remove protection.

```bash
ai-guard remove path/to/file.py
ai-guard remove path/to/file.py:my_function
```

### `ai-guard list`

Show all protected entries.

### `ai-guard verify`

Check all protected code for modifications. Returns exit code 1 if any protected code has changed.

### `ai-guard install-hook`

Install a git pre-commit hook that runs `ai-guard verify` before each commit.

## The `.ai-guard` File

Protection entries are stored in `.ai-guard` at the project root:

```
src/auth.py:8a3b2c1d4e5f6789
src/billing.py:calculate_tax:1234567890abcdef
tests/test_core.py:test_invariant_one:abcdef1234567890
tests/test_core.py:test_invariant_two:fedcba0987654321
```

Format:
- `path:hash` - whole file protection
- `path:identifier:hash` - identifier protection

## What Gets Hashed

For **files**: the entire file content.

For **identifiers**: everything that defines the identifier:
- Decorators
- Signature (name, parameters, return type annotation)
- Docstring
- Body

This means changing any of these will trigger a protection violation.

## Adding Language Support

ai-guard has a pluggable parser system. Currently Python is supported via the built-in `ast` module.

To add support for another language, create a parser that implements the `Parser` interface:

```python
from ai_guard.parsers.base import Parser, Identifier, register_parser

class JavaScriptParser(Parser):
    def extract_identifier(self, source: str, name: str) -> Optional[Identifier]:
        # Parse source and find the identifier
        ...

    def list_identifiers(self, source: str) -> list[Identifier]:
        # Return all top-level identifiers
        ...

# Register for file extensions
register_parser(['.js', '.jsx'], JavaScriptParser)
```

See `ai_guard/parsers/python.py` for a complete example.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run specific test file
pytest tests/test_file_protection.py -v
```

## License

MIT
