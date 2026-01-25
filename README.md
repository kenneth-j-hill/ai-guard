# ai-guard

Protect code from incidental modifications by an AI.

## Overview

When working with AI coding assistants, certain code should never be modified without explicit human approval - security-critical functions, tested invariants, configuration that must stay stable. ai-guard lets you mark this code as protected and enforces it through git hooks.

### Goals

- **Visibility** - Make it obvious when protected code has been changed, whether intentionally or accidentally
- **Speed bumps, not walls** - Create friction that catches incidental modifications before they're committed
- **Human-in-the-loop** - Require explicit human action (`ai-guard update`) to approve changes to protected code

### Non-goals

- **Security against malicious actors** - A determined attacker (human or AI) can bypass these protections
- **Replacement for code review** - This is an additional layer, not a substitute for proper review processes
- **Guaranteed protection** - This tool reduces risk but cannot eliminate it

### Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. ai-guard is a development tool designed to reduce accidental modifications, not a security product. It can be bypassed and should not be relied upon as your only safeguard. Always use proper code review, version control, backups, and security practices. The authors are not liable for any damages arising from the use of this software or from modifications to code that was intended to be protected. See the LICENSE file for full terms.

## Features

- **File-level protection** - Protect entire files from modification
- **Identifier-level protection** - Protect specific functions, classes, or variables
- **Wildcard patterns** - Protect groups of identifiers (e.g., `test_invariant_*`)
- **Git integration** - Pre-commit hook blocks commits that modify protected code
- **Self-protection** - The `.ai-guard` file protects itself from tampering
- **Extensible** - Pluggable parser system for language support (Python and C/C++ included)

## Installation

```bash
pip install ai-guard
```

Ensure the install location is in your PATH. Common approaches:

- **pipx** (recommended): `pipx install ai-guard` - installs in isolated environment, automatically adds to PATH
- **User install**: `pip install --user ai-guard` - installs to `~/.local/bin` (add to PATH if needed)
- **Virtual environment**: activate the venv before running ai-guard commands
- **System install**: `sudo pip install ai-guard` - not recommended, but works

Verify installation:

```bash
ai-guard --version
```

For development:

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

# Protect multiple targets at once
ai-guard add src/auth.py src/billing.py:calculate_tax

# Use glob patterns (quote to prevent shell expansion)
ai-guard add "src/*.py" "tests/*.py:test_*"

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

### `ai-guard add <target> [target ...]`

Add protection for files or identifiers. Accepts multiple targets and glob patterns.

```bash
# Whole file
ai-guard add path/to/file.py

# Specific identifier (function, class, variable)
ai-guard add path/to/file.py:my_function

# Wildcard pattern for identifiers
ai-guard add path/to/file.py:test_*

# Multiple targets
ai-guard add file1.py file2.py:func

# Glob patterns (quote to prevent shell expansion)
ai-guard add "src/*.py" "tests/*.py:Test*"
```

### `ai-guard update <target> [target ...]`

Update the hash after intentionally modifying protected code. Accepts multiple targets and glob patterns.

```bash
ai-guard update path/to/file.py
ai-guard update path/to/file.py:my_function
ai-guard update "src/*.py"
```

### `ai-guard remove <target> [target ...]`

Remove protection. Accepts multiple targets and glob patterns.

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

## Hardening Protection

The pre-commit hook alone only catches incidental modifications. An AI with commit permissions that sees the hook failure message could follow its instructions to run `ai-guard update` and recommit. For effective protection, you must also block the bypass commands.

### Install ai-guard outside the working tree

Install ai-guard in a location the AI cannot modify, such as your home directory or system site-packages:

```bash
pip install ai-guard              # System/user install
pipx install ai-guard             # Isolated install
```

Avoid installing in editable mode (`pip install -e .`) within the project, as the AI could modify the source.

### Block bypass commands

The critical step is preventing the AI from running `ai-guard update` or `ai-guard remove`. Without this, the pre-commit hook is only a speed bump.

#### Claude Code

Add to `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Bash(ai-guard update*)",
      "Bash(ai-guard remove*)",
      "Edit(.ai-guard)",
      "Write(.ai-guard)"
    ]
  }
}
```

#### Other AI tools

Configure your AI tool to deny commands matching:
- `ai-guard update`
- `ai-guard remove`
- Direct writes to `.ai-guard`

With bypass commands blocked, the AI cannot resolve protection violations, and the commit will fail. A human must review the change and explicitly run `ai-guard update` to approve it.

## Supported Languages

- **Python** - Full support via the built-in `ast` module
- **C/C++** - Support via regex-based parsing (GCC/G++)

## Adding Language Support

ai-guard has a pluggable parser system.

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

## Requirements

- Python 3.9+
- Git (for pre-commit hook)

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Trademark

"ai-guard" is a trademark. Derivative works may not use the name "ai-guard" or imply endorsement without permission. Attribution to the original project is required per the Apache 2.0 license.

## Contributing

Contributions are welcome! Please run the test suite before submitting:

```bash
pytest
```

The tests also serve as documentation for the expected behavior.
