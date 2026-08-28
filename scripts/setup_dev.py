"""Create a per-machine development venv; never run the production bot."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true",
                        help="Use already installed dependencies (offline verification).")
    args = parser.parse_args()
    if sys.version_info[:2] not in ((3, 11), (3, 12)):
        parser.error("Use Python 3.11 (preferred) or 3.12; do not use the old system Python.")
    env_dir = ROOT / ".venv"
    python = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if env_dir.exists():
        if not python.is_file():
            parser.error("Existing .venv is incomplete. Leave it intact and use a fresh clone.")
        version = subprocess.check_output(
            [str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            text=True).strip()
        if version != "%d.%d" % sys.version_info[:2]:
            parser.error("Existing .venv uses another Python version. Use a fresh clone.")
    else:
        if args.skip_install:
            parser.error("--skip-install requires an existing .venv.")
        subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
    if not args.skip_install:
        subprocess.run([str(python), "-m", "pip", "install", "-r",
                        str(ROOT / "requirements-dev.txt")], cwd=ROOT, check=True)
    subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / "scripts/check_dev.py")], cwd=ROOT, check=True)
    local_dir = ROOT / ".local"
    local_dir.mkdir(exist_ok=True)
    packages = subprocess.check_output([str(python), "-m", "pip", "freeze"], text=True)
    (local_dir / "installed-packages.txt").write_text(packages, encoding="utf-8")
    (local_dir / "setup.json").write_text(json.dumps({
        "python": str(python), "version": sys.version.split()[0],
        "note": "Local development only. No live bot run or Discord delivery."
    }, indent=2), encoding="utf-8")
    print("Ready. Open this repository folder in Codex: " + str(ROOT))


if __name__ == "__main__":
    main()
