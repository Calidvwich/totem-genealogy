import os
import subprocess
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DATABASE = os.getenv("TOTEM_DATABASE", "genealogy")
TOTEM_DUMP = os.getenv("TOTEM_DUMP", "/usr/local/totem/bin/totem_dump")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")
OUTPUT = APP_DIR / f"{DATABASE}_bck.sql"


def main() -> None:
    with OUTPUT.open("w", encoding="utf-8") as handle:
        command = [TOTEM_DUMP]
        if TOTEM_PORT:
            command.extend(["-p", TOTEM_PORT])
        if TOTEM_USER:
            command.extend(["-U", TOTEM_USER])
        command.append(DATABASE)
        completed = subprocess.run(command, stdout=handle, universal_newlines=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    print(f"exported {OUTPUT}")


if __name__ == "__main__":
    main()
