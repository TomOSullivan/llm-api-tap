"""Install / remove / check the mitmproxy CA for the tap (original Second Wind code).

Usage
  python install_ca.py status  [--confdir PATH]
  python install_ca.py install [--confdir PATH]     Windows: certutil -user (a dialog may appear)
  python install_ca.py remove  [--thumbprint TP | --confdir PATH]

Install puts the CA in the CURRENT USER store only, never the machine store. Remove
deletes exactly one thumbprint. macOS/Linux: prints manual instructions.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tapkit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "install", "remove"])
    ap.add_argument("--confdir", default=str(Path.home() / ".mitmproxy"))
    ap.add_argument("--thumbprint")
    a = ap.parse_args()
    confdir = Path(a.confdir).expanduser()
    ca_pem, ca_cer = tapkit.ca_paths(confdir)

    if a.command == "status":
        if not ca_pem.exists():
            print(f"no mitmproxy CA at {ca_pem} (run the proxy once to generate it)")
            return 1
        tp = tapkit.thumbprint_pem(ca_pem.read_bytes())
        print(f"CA: {ca_pem}")
        print(f"thumbprint (SHA-1): {tp}")
        if sys.platform == "win32":
            print(f"in CurrentUser\\Root: {tp in tapkit.store_thumbprints_windows()}")
        else:
            print("store check not implemented on this platform; see SKILL.md")
        return 0

    if a.command == "install":
        if not ca_cer.exists():
            print(f"no CA certificate at {ca_cer}; run the proxy once first")
            return 1
        if sys.platform != "win32":
            print("automated install supports Windows only; on macOS run:")
            print(f'  security add-trusted-cert -d -r trustRoot -k ~/Library/Keychains/login.keychain-db "{ca_pem}"')
            print("on Linux, follow your distribution's update-ca-certificates procedure")
            return 2
        tp = tapkit.thumbprint_pem(ca_pem.read_bytes())
        if tp in tapkit.store_thumbprints_windows():
            print(f"already installed (thumbprint {tp})")
            return 0
        print("installing into CurrentUser\\Root; accept the Windows confirmation dialog if one appears...")
        r = subprocess.run(["certutil", "-user", "-addstore", "Root", str(ca_cer)])
        if r.returncode != 0:
            print("certutil failed")
            return 1
        ok = tp in tapkit.store_thumbprints_windows()
        print(f"installed: {ok} (thumbprint {tp})")
        return 0 if ok else 1

    if a.command == "remove":
        tp = a.thumbprint
        if not tp:
            if not ca_pem.exists():
                print("give --thumbprint TP (no CA found to read it from)")
                return 2
            tp = tapkit.thumbprint_pem(ca_pem.read_bytes())
        if sys.platform != "win32":
            print("automated removal supports Windows only; use Keychain Access / update-ca-certificates")
            return 2
        if tp not in tapkit.store_thumbprints_windows():
            print(f"thumbprint {tp} is not in CurrentUser\\Root; nothing to remove")
            return 0
        r = subprocess.run(["certutil", "-user", "-delstore", "Root", tp])
        if r.returncode != 0:
            print("certutil failed")
            return 1
        gone = tp not in tapkit.store_thumbprints_windows()
        print(f"removed: {gone}")
        return 0 if gone else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
