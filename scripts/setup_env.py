"""Create the skill's virtualenv and install mitmproxy (original Second Wind code).

Usage: python setup_env.py [--recreate]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tapkit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true")
    a = ap.parse_args()
    vpy = tapkit.venv_python()
    if vpy and not a.recreate:
        print(f"venv already exists: {tapkit.VENV}")
    else:
        if tapkit.VENV.exists():
            shutil.rmtree(tapkit.VENV)
        print(f"creating venv at {tapkit.VENV} ...")
        subprocess.run([sys.executable, "-m", "venv", str(tapkit.VENV)], check=True)
        vpy = tapkit.venv_python()
    print("installing mitmproxy (cached after the first run)...")
    subprocess.run([str(vpy), "-m", "pip", "install", "--disable-pip-version-check", "-q", "mitmproxy"], check=True)
    out = subprocess.run([str(tapkit.venv_bin("mitmdump")), "--version"], capture_output=True, text=True, timeout=60)
    print((out.stdout or out.stderr).strip().splitlines()[0])
    print("ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
