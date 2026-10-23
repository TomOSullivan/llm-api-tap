"""Turn the Claude Code traffic tap off (original Second Wind code).

Restores the backed-up settings file byte-for-byte, stops the proxy, and with --remove-ca
removes the mitmproxy CA from the user certificate store by its recorded thumbprint.

Usage: python tap_off.py [--remove-ca]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tapkit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remove-ca", action="store_true")
    a = ap.parse_args()
    if not tapkit.STATE.exists():
        print(f"no tap state at {tapkit.STATE}; nothing to do")
        return 0
    state = json.loads(tapkit.STATE.read_text(encoding="utf-8"))
    problems = []

    backup = Path(state["backup"]) if state.get("backup") else None
    settings = Path(state["settings"])
    try:
        tapkit.unwire_settings(settings, backup)
        print(f"settings restored: {settings}")
    except Exception as ex:
        problems.append(f"settings restore failed: {ex}")

    try:
        tapkit.kill_tree(int(state["pid"]))
        print(f"proxy stopped (pid {state['pid']})")
    except Exception as ex:
        problems.append(f"proxy stop failed: {ex}")

    if a.remove_ca:
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "install_ca.py"),
                            "remove", "--thumbprint", state.get("ca_thumbprint", "")])
        if r.returncode != 0:
            problems.append("CA removal failed; run scripts/install_ca.py remove --thumbprint "
                            + state.get("ca_thumbprint", ""))
        else:
            print("CA removed from the user store")

    tapkit.STATE.unlink()
    port = state.get("port")
    if port and tapkit.port_open(int(port)):
        problems.append(f"port {port} still open; the proxy may not have stopped")
    if problems:
        for p in problems:
            print(f"WARNING {p}")
        return 1
    print("tap off. Captures kept at: " + state.get("out", "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
