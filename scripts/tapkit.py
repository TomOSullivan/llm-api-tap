"""Shared helpers for the llm-api-tap scripts (original Second Wind code)."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
VENV = SKILL_ROOT / "venv"
STATE = SKILL_ROOT / "tap-state.json"
DEFAULT_CAPTURES = SKILL_ROOT / "captures"
ENV_KEYS = ("HTTPS_PROXY", "NO_PROXY", "NODE_EXTRA_CA_CERTS")


def venv_python():
    p = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return p if p.exists() else None


def venv_bin(name: str):
    p = VENV / ("Scripts" if os.name == "nt" else "bin") / (name + (".exe" if os.name == "nt" else ""))
    return p if p.exists() else None


def find_mitmdump():
    return venv_bin("mitmdump") or shutil.which("mitmdump")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def read_settings(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except FileNotFoundError:
        return {}


def wire_settings(path: Path, proxy: str, no_proxy: str, ca_pem: Path) -> Path:
    backup = Path(str(path) + ".tap-backup")
    if backup.exists():
        raise SystemExit(f"backup already exists ({backup}); is the tap already on? Run tap_off.py first.")
    original = path.read_bytes() if path.exists() else b"{}\n"
    backup.write_bytes(original)
    data = json.loads(original.decode("utf-8-sig") or "{}")
    env = data.setdefault("env", {})
    env["HTTPS_PROXY"] = proxy
    env["NO_PROXY"] = no_proxy
    env["NODE_EXTRA_CA_CERTS"] = str(ca_pem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return backup


def unwire_settings(path: Path, backup) -> bool:
    if backup is not None and Path(backup).exists():
        path.write_bytes(Path(backup).read_bytes())
        Path(backup).unlink()
        return True
    data = read_settings(path)
    env = data.get("env") or {}
    changed = False
    for key in ENV_KEYS:
        if key in env:
            del env[key]
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def thumbprint_pem(pem_bytes: bytes) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    cert = x509.load_pem_x509_certificate(pem_bytes)
    return cert.fingerprint(hashes.SHA1()).hex().upper()


def ca_paths(confdir: Path):
    return confdir / "mitmproxy-ca-cert.pem", confdir / "mitmproxy-ca-cert.cer"


def store_thumbprints_windows():
    ps = ("Get-ChildItem Cert:\\CurrentUser\\Root | Where-Object { $_.Subject -like '*mitmproxy*' } "
          "| ForEach-Object { $_.Thumbprint }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
