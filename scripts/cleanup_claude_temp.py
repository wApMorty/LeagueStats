"""
Cleanup script for Claude Code temporary files.

These tmpclaude-*-cwd files are created by Claude Code during command execution
but sometimes aren't automatically cleaned up. This script removes them.

Usage:
    python scripts/cleanup_claude_temp.py
"""

import os
import glob
from pathlib import Path


def cleanup_claude_temp_files(root_dir: str = ".") -> int:
    """
    Remove all tmpclaude-*-cwd temporary files.

    Args:
        root_dir: Root directory to search (default: current directory)

    Returns:
        Number of files removed
    """
    pattern = os.path.join(root_dir, "tmpclaude-*-cwd")
    temp_files = glob.glob(pattern)

    count = 0
    for file_path in temp_files:
        try:
            os.remove(file_path)
            count += 1
            print(f"[OK] Removed: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"[ERROR] Failed to remove {os.path.basename(file_path)}: {e}")

    return count


def main():
    """Main entry point."""
    print("[CLEANUP] Claude Code Temp File Cleanup")
    print("=" * 50)

    # Get project root (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Change to project root
    os.chdir(project_root)

    # Cleanup
    removed = cleanup_claude_temp_files()

    print("=" * 50)
    if removed > 0:
        print(f"[SUCCESS] Cleaned up {removed} temporary file(s)")
    else:
        print("[SUCCESS] No temporary files found - workspace is clean!")


if __name__ == "__main__":
    main()
