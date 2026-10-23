"""Turn on the Claude Code traffic tap (original Second Wind code).

Starts a loopback mitmproxy forward proxy, wires the Claude settings file (with an exact
backup), and optionally installs the mitmproxy CA into the user certificate store. Only
NEW Claude Code sessions pick up the settings. Full usage and safety notes: SKILL.md.

Usage
  python tap_on.py [--port 8090] [--web-port 8081] [--no-web] [--out DIR] [--settings PATH]
                   [--confdir PATH] [--hosts LIST] [--install-ca]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tapkit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--web-port", type=int, default=8081)
    ap.add_argument("--no-web", action="store_true", help="run mitmdump (no web UI)")
    ap.add_argument("--out", default=str(tapkit.DEFAULT_CAPTURES))
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    ap.add_argument("--confdir", default=str(Path.home() / ".mitmproxy"))
    ap.add_argument("--hosts", help="comma-separated host suffixes to capture")
    ap.add_argument("--install-ca", action="store_true")
    a = ap.parse_args()

    if tapkit.STATE.exists():
        print(f"tap state already exists: {tapkit.STATE} - run tap_off.py first")
        return 2
    exe = tapkit.venv_bin("mitmdump") if a.no_web else tapkit.venv_bin("mitmweb")
    if exe is None:
        print("mitmproxy not found in the skill venv; run setup_env.py first")
        return 2
    if tapkit.port_open(a.port):
        print(f"port {a.port} is already in use; pass --port")
        return 2

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    confdir = Path(a.confdir).expanduser().resolve()
    settings = Path(a.settings).expanduser()
    ca_pem, ca_cer = tapkit.ca_paths(confdir)

    cmd = [str(exe), "--mode", "regular", "--listen-host", "127.0.0.1",
           "--listen-port", str(a.port), "-s", str(Path(__file__).parent / "capture_addon.py"),
           "--set", f"confdir={confdir}", "--set", "termlog_verbosity=warn"]
    if not a.no_web:
        cmd += ["--web-host", "127.0.0.1", "--web-port", str(a.web_port),
                "--set", "web_open_browser=false"]

    env = {**os.environ, "CC_TAP_OUT": str(out)}
    if a.hosts:
        env["CC_TAP_HOSTS"] = a.hosts
    creationflags = (0x00000008 | 0x00000200) if os.name == "nt" else 0  # DETACHED | NEW_PROCESS_GROUP
    log = open(out / "mitmweb.log", "ab")
    proc = subprocess.Popen(cmd, stdout=log, stderr=log, cwd=str(out), env=env,
                            creationflags=creationflags)

    if not tapkit.wait_port(a.port, 30):
        proc.terminate()
        print(f"proxy did not start on port {a.port}; see {out / 'mitmweb.log'}")
        return 1

    deadline = 15
    import time
    for _ in range(deadline * 4):
        if ca_pem.exists():
            break
        time.sleep(0.25)
    if not ca_pem.exists():
        proc.terminate()
        print(f"CA was not created at {ca_pem}")
        return 1

    backup = tapkit.wire_settings(settings, f"http://127.0.0.1:{a.port}",
                                  "localhost,127.0.0.1,::1", ca_pem)
    state = {
        "pid": proc.pid, "port": a.port,
        "web_port": None if a.no_web else a.web_port,
        "out": str(out), "settings": str(settings), "backup": str(backup),
        "confdir": str(confdir), "ca_pem": str(ca_pem), "ca_cer": str(ca_cer),
        "ca_thumbprint": tapkit.thumbprint_pem(ca_pem.read_bytes()),
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tapkit.STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"proxy:    127.0.0.1:{a.port} (pid {proc.pid})")
    if not a.no_web:
        print(f"web UI:   http://127.0.0.1:{a.web_port}")
    print(f"captures: {out}")
    print(f"settings: {settings} (backup: {backup})")
    print(f"CA:       {ca_pem} (thumbprint {state['ca_thumbprint']})")
    if a.install_ca:
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "install_ca.py"),
                            "install", "--confdir", str(confdir)])
        if r.returncode != 0:
            print("WARNING: CA install failed; run scripts/install_ca.py install")
    else:
        print("next: install the CA (scripts/install_ca.py install) if not trusted yet,")
        print("      then start a NEW Claude Code session - existing sessions keep old settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
