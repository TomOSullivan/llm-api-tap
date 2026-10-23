"""Check the tap environment and current state (read-only; original Second Wind code).

Usage: python doctor.py [--json]
Exit code 0 when every check passes, 1 otherwise.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tapkit


def main() -> int:
    as_json = "--json" in sys.argv
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    check("python", sys.version_info >= (3, 10), sys.version.split()[0])
    vpy = tapkit.venv_python()
    check("skill venv", vpy is not None, str(tapkit.VENV) if vpy else "missing; run scripts/setup_env.py")
    mitmdump = tapkit.find_mitmdump()
    check("mitmproxy", mitmdump is not None, str(mitmdump) if mitmdump else "not installed")
    if mitmdump:
        try:
            out = subprocess.run([str(mitmdump), "--version"], capture_output=True, text=True, timeout=30)
            version = next((ln for ln in (out.stdout or out.stderr).splitlines() if "Mitmproxy" in ln), "")
            check("mitmproxy version", bool(version), version)
        except Exception as ex:
            check("mitmproxy version", False, str(ex))

    state = None
    if tapkit.STATE.exists():
        try:
            state = json.loads(tapkit.STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    check("tap state", True, "on (started " + state.get("started_utc", "?") + ")" if state else "off")

    settings = Path(state["settings"]) if state else Path.home() / ".claude" / "settings.json"
    env = (tapkit.read_settings(settings).get("env")) or {}
    wired = "HTTPS_PROXY" in env and "NODE_EXTRA_CA_CERTS" in env
    detail = f"{settings} HTTPS_PROXY={env.get('HTTPS_PROXY', '-')}"
    if state:
        check("settings wired", wired, detail)
    elif wired:
        check("settings wired", True, detail + " (wired by an external tap; no skill state file)")
    else:
        check("settings wired", True, "not wired (tap off)")

    confdir = Path(state["confdir"]) if state else Path.home() / ".mitmproxy"
    ca_pem, _ = tapkit.ca_paths(confdir)
    check("CA file", ca_pem.exists() or state is None, str(ca_pem) if ca_pem.exists() else "absent (generated on first proxy run)")
    if ca_pem.exists():
        tp = tapkit.thumbprint_pem(ca_pem.read_bytes())
        if sys.platform == "win32":
            check("CA in user store", tp in tapkit.store_thumbprints_windows(), tp)
        else:
            check("CA in user store", True, "not checked on this platform")

    if state:
        check("proxy listening", tapkit.port_open(int(state["port"])), f"127.0.0.1:{state['port']}")

    if as_json:
        print(json.dumps(checks, indent=2))
    else:
        for c in checks:
            print(f"  {'OK ' if c['ok'] else '!! '} {c['name']}: {c['detail']}")
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
