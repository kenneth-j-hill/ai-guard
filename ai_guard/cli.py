"""Command-line interface for ai-guard."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ai_guard.core import GuardFile


def find_project_root(start: Optional[Path] = None) -> Path:
    """Find the project root by looking for .git directory.

    Args:
        start: Directory to start searching from. Defaults to cwd.

    Returns:
        The project root directory.
    """
    if start is None:
        start = Path.cwd()
    current = start.resolve()

    # Check current directory first
    if (current / ".git").exists():
        return current

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fall back to current directory
    return start.resolve()


def parse_target(target: str) -> tuple[str, Optional[str]]:
    """Parse a target string into path and optional identifier.

    Args:
        target: Target in format 'path/to/file.py' or 'path/to/file.py:identifier'

    Returns:
        Tuple of (path, identifier or None)
    """
    # Handle the case where there might be a colon in the path (Windows drive letter)
    # But since we normalize to forward slashes, we can just split on the last colon
    # after the file extension
    if ":" in target:
        # Find the .py (or similar) extension and split after it
        for ext in [".py", ".pyw", ".js", ".ts", ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx", ".hxx"]:
            if ext + ":" in target:
                idx = target.index(ext + ":") + len(ext)
                path = target[:idx]
                identifier = target[idx + 1:]
                return path, identifier if identifier else None
    return target, None


def expand_glob_target(root: Path, target: str) -> list[tuple[str, Optional[str]]]:
    """Expand a target with glob patterns in the path.

    Args:
        root: Project root directory.
        target: Target like 'tests/*.py:func' or 'src/**/*.py'

    Returns:
        List of (path, identifier) tuples for each matching file.
    """
    import glob

    path, identifier = parse_target(target)

    # Check if path contains glob characters
    if "*" not in path and "?" not in path:
        return [(path, identifier)]

    # Expand the glob relative to root
    full_pattern = str(root / path)
    matches = glob.glob(full_pattern, recursive=True)

    if not matches:
        return [(path, identifier)]  # Return as-is, will error later

    # Convert back to relative paths
    results = []
    for match in sorted(matches):
        rel_path = str(Path(match).relative_to(root))
        # Normalize to forward slashes
        rel_path = rel_path.replace("\\", "/")
        results.append((rel_path, identifier))

    return results


def cmd_add(args: argparse.Namespace) -> int:
    """Add protection for a file or identifier."""
    root = find_project_root()
    guard = GuardFile(root)

    any_success = False
    any_error = False

    for target in args.targets:
        for path, identifier in expand_glob_target(root, target):
            try:
                if identifier:
                    entries = guard.add_identifier(path, identifier)
                    for entry in entries:
                        print(f"Protected {entry.path}:{entry.identifier} ({entry.hash})")
                        any_success = True
                else:
                    entry = guard.add_file(path)
                    print(f"Protected {entry.path} ({entry.hash})")
                    any_success = True
            except FileNotFoundError:
                print(f"Error: File not found: {path}", file=sys.stderr)
                any_error = True
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                any_error = True

    if any_success:
        guard.save()

    return 1 if any_error and not any_success else 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update the hash for a protected entry."""
    root = find_project_root()
    guard = GuardFile(root)

    any_success = False
    any_error = False

    for target in args.targets:
        for path, identifier in expand_glob_target(root, target):
            try:
                entries = guard.update(path, identifier)
                for entry in entries:
                    if entry.identifier:
                        print(f"Updated {entry.path}:{entry.identifier} ({entry.hash})")
                    else:
                        print(f"Updated {entry.path} ({entry.hash})")
                    any_success = True
            except FileNotFoundError:
                print(f"Error: File not found: {path}", file=sys.stderr)
                any_error = True
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                any_error = True

    if any_success:
        guard.save()

    return 1 if any_error and not any_success else 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Remove protection for a file or identifier."""
    root = find_project_root()
    guard = GuardFile(root)

    total_count = 0
    for target in args.targets:
        for path, identifier in expand_glob_target(root, target):
            count = guard.remove(path, identifier)
            total_count += count

    if total_count > 0:
        guard.save()
        print(f"Removed {total_count} protection(s)")
        return 0
    else:
        print("No matching protections found", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all protected entries."""
    root = find_project_root()
    guard = GuardFile(root)

    entries = guard.list_entries()
    if not entries:
        print("No protected entries")
        return 0

    for entry in entries:
        if entry.identifier:
            print(f"{entry.path}:{entry.identifier} ({entry.hash})")
        else:
            print(f"{entry.path} ({entry.hash})")

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify all protected entries."""
    root = find_project_root()
    guard = GuardFile(root)

    failures = guard.verify()

    if not failures:
        print("All protected code verified successfully")
        return 0

    print("AI-Guard violations found:", file=sys.stderr)
    for entry, reason in failures:
        if entry.identifier:
            print(f"  {entry.path}:{entry.identifier} - {reason}", file=sys.stderr)
        else:
            print(f"  {entry.path} - {reason}", file=sys.stderr)

    return 1


def cmd_install_hook(args: argparse.Namespace) -> int:
    """Install the git pre-commit hook."""
    root = find_project_root()
    hooks_dir = root / ".git" / "hooks"

    if not hooks_dir.exists():
        print("Error: .git/hooks directory not found", file=sys.stderr)
        return 1

    hook_path = hooks_dir / "pre-commit"

    hook_content = '''#!/bin/sh
# ai-guard pre-commit hook
# Prevents commits that modify protected code

ai-guard verify
if [ $? -ne 0 ]; then
    echo ""
    echo "Commit blocked: Protected code was modified."
    echo "If this change is intentional, run 'ai-guard update <path>' first."
    exit 1
fi
'''

    # Check if hook already exists
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if "ai-guard" in existing:
            print("ai-guard hook already installed")
            return 0
        else:
            # Append to existing hook
            hook_content = existing.rstrip() + "\n\n" + hook_content
            print("Appending ai-guard to existing pre-commit hook")
    else:
        print("Installing pre-commit hook")

    hook_path.write_text(hook_content, encoding="utf-8")
    hook_path.chmod(0o755)

    print(f"Hook installed at {hook_path}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="ai-guard",
        description="Protect code from incidental modifications by an AI",
        epilog="Run 'ai-guard <command> --help' for help on a specific command.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('ai_guard').__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # add command
    add_parser = subparsers.add_parser(
        "add", help="Add protection for a file or identifier"
    )
    add_parser.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help='File or path:identifier to protect. Supports globs: "src/*.py:func_*" (quote to prevent shell expansion)',
    )
    add_parser.set_defaults(func=cmd_add)

    # update command
    update_parser = subparsers.add_parser(
        "update", help="Update the hash for a protected entry"
    )
    update_parser.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help='File or path:identifier to update. Supports globs: "src/*.py:func_*"',
    )
    update_parser.set_defaults(func=cmd_update)

    # remove command
    remove_parser = subparsers.add_parser(
        "remove", help="Remove protection for a file or identifier"
    )
    remove_parser.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help="File path or path:identifier to unprotect",
    )
    remove_parser.set_defaults(func=cmd_remove)

    # list command
    list_parser = subparsers.add_parser("list", help="List all protected entries")
    list_parser.set_defaults(func=cmd_list)

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify all protected entries")
    verify_parser.set_defaults(func=cmd_verify)

    # install-hook command
    install_parser = subparsers.add_parser(
        "install-hook", help="Install the git pre-commit hook"
    )
    install_parser.set_defaults(func=cmd_install_hook)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
