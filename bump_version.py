"""
bump_version.py
Reads APP_VERSION from src/version.py, then writes back an incremented version
using the YYYYMMDD.NN scheme:
  - Same day as current version  ->  increments NN   (e.g. 20260304.01 -> 20260304.02)
  - New day                       ->  resets  to  01  (e.g. 20260304.02 -> 20260305.01)
Run automatically via ship.ps1 before every git push.
"""
import re
from datetime import date
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "src" / "version.py"


def bump():
    today = date.today().strftime("%Y%m%d")
    content = VERSION_FILE.read_text(encoding="utf-8")

    match = re.search(r'APP_VERSION\s*=\s*["\'](\d{8})\.(\d+)["\']', content)
    if match:
        file_date = match.group(1)
        counter = int(match.group(2))
        new_counter = counter + 1 if file_date == today else 1
    else:
        new_counter = 1

    new_version = f"{today}.{new_counter:02d}"
    new_content = re.sub(
        r'APP_VERSION\s*=\s*["\'][\d.]+["\']',
        f'APP_VERSION = "{new_version}"',
        content,
    )
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    print(f"Version bumped to: {new_version}")
    return new_version


if __name__ == "__main__":
    bump()
