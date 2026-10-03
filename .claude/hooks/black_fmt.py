"""Hook PostToolUse (Edit|Write) : formate avec Black le fichier .py que Claude vient de modifier."""

import json
import subprocess
import sys


def main() -> None:
    path = (json.load(sys.stdin).get("tool_input") or {}).get("file_path", "")
    path = path.replace("\\", "/")
    if not path.endswith(".py") or "/alembic/versions/" in path:
        return
    subprocess.run([sys.executable, "-m", "black", "-q", path], check=False)


if __name__ == "__main__":
    main()
