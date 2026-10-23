#!/usr/bin/env python
"""Self-tests for the llm-api-tap skill (original Second Wind code).

Sandbox rules: ephemeral ports and temp directories only; never touches real ~/.claude
settings, the real ~/.mitmproxy CA, certificate stores, or Anthropic. Run with the skill
venv python:

  venv/Scripts/python.exe tests/run_tests.py      (Windows)
  venv/bin/python tests/run_tests.py              (macOS/Linux)
"""
from __future__ import annotations

import datetime
import http.server
import importlib.util
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import tapkit  # noqa: E402

RESULTS = []


class Skip(Exception):
    pass


def test(fn):
    def runner(*args):
        try:
            fn(*args)
            RESULTS.append((fn.__name__, "PASS", ""))
            print(f"PASS  {fn.__name__}")
        except Skip as ex:
            RESULTS.append((fn.__name__, "SKIP", str(ex)))
            print(f"SKIP  {fn.__name__}: {ex}")
        except Exception as ex:
            RESULTS.append((fn.__name__, "FAIL", f"{type(ex).__name__}: {ex}"))
            print(f"FAIL  {fn.__name__}: {type(ex).__name__}: {ex}")
    runner.__name__ = fn.__name__
    return runner


def load_addon():
    spec = importlib.util.spec_from_file_location("capture_addon", SCRIPTS / "capture_addon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh(work, name):
    d = work / name
    d.mkdir(parents=True, exist_ok=True)
    os.environ["CC_TAP_OUT"] = str(d)
    return d


def wait_for(pred, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.25)
    return False


def read_index(out):
    p = Path(out) / "index.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]


def index_has(out, host, path):
    return any(e.get("host") == host and (e.get("path") or "").startswith(path) for e in read_index(out))


def latest_meta(out, path):
    for e in reversed(read_index(out)):
        if (e.get("path") or "").startswith(path):
            return json.loads((Path(out) / f"{e['id']}-meta.json").read_text(encoding="utf-8"))
    raise AssertionError(f"no meta captured for {path}")


def make_cert(work, cn):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2040, 1, 1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_p, key_p = work / "srv-cert.pem", work / "srv-key.pem"
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_p.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.TraditionalOpenSSL,
                                        serialization.NoEncryption()))
    return cert_p, key_p


@test
def addon_redacts_credentials(work):
    from mitmproxy import http
    out = fresh(work, "redact")
    os.environ["CC_TAP_HOSTS"] = "api.anthropic.com"
    addon = load_addon()
    req = http.Request.make("POST", "https://api.anthropic.com/v1/messages?beta=true",
                            content=b'{"model": "claude-opus-5-5", "stream": false}',
                            headers={"content-type": "application/json",
                                     "authorization": "Bearer sk-live-secret",
                                     "x-api-key": "sk-ant-secret",
                                     "cookie": "session=xyz"})
    flow = http.HTTPFlow(None, None)
    flow.request = req
    flow.response = http.Response.make(200, b'{"ok": true}', {"content-type": "application/json"})
    addon.request(flow)
    addon.response(flow)
    files = sorted(p.name for p in out.iterdir())
    assert any(n.endswith("-request.json") for n in files), files
    meta = next(p for p in out.iterdir() if p.name.endswith("-meta.json"))
    data = json.loads(meta.read_text(encoding="utf-8"))
    rh = data["request_headers"]
    assert rh["authorization"] == "[omitted]" and rh["x-api-key"] == "[omitted]" and rh["cookie"] == "[omitted]", rh
    assert data["status"] == 200 and data["model"] == "claude-opus-5-5", data
    idx = read_index(out)
    assert idx and idx[-1]["path"].startswith("/v1/messages"), idx


@test
def addon_tees_sse(work):
    from mitmproxy import http
    out = fresh(work, "sse")
    os.environ["CC_TAP_HOSTS"] = "api.anthropic.com"
    addon = load_addon()
    flow = http.HTTPFlow(None, None)
    flow.request = http.Request.make("POST", "https://api.anthropic.com/v1/messages",
                                     content=b'{"model": "m", "stream": true}',
                                     headers={"content-type": "application/json"})
    flow.response = http.Response.make(200, b"", {"content-type": "text/event-stream"})
    addon.request(flow)
    addon.responseheaders(flow)
    tee = flow.response.stream
    assert callable(tee), "SSE tee not installed"
    tee(b'data: {"type": "message_start"}\n\n')
    tee(b'data: {"type": "message_delta"}\n\n')
    addon.response(flow)
    sse = next(p for p in out.iterdir() if p.name.endswith("-response.sse.txt"))
    text = sse.read_text(encoding="utf-8")
    assert "message_start" in text and "message_delta" in text, text
    meta = json.loads(next(p for p in out.iterdir() if p.name.endswith("-meta.json")).read_text(encoding="utf-8"))
    assert meta["streamed"] is True, meta


@test
def addon_host_filter(work):
    from mitmproxy import http
    out = fresh(work, "filter")
    os.environ["CC_TAP_HOSTS"] = "api.anthropic.com"
    addon = load_addon()
    before = sorted(p.name for p in out.iterdir())
    flow = http.HTTPFlow(None, None)
    flow.request = http.Request.make("GET", "https://example.com/x", content=b"",
                                     headers={"content-type": "text/plain"})
    flow.response = http.Response.make(200, b"nope", {"content-type": "text/plain"})
    addon.request(flow)
    addon.response(flow)
    assert sorted(p.name for p in out.iterdir()) == before, "unwanted host was captured"


@test
def settings_wiring_round_trip(work):
    tap_on = importlib.import_module("tap_on")
    sp = work / "settings.json"
    sp.write_text('{\n  "model": "opus"\n}\n', encoding="utf-8")
    original = sp.read_bytes()
    backup = tapkit.wire_settings(sp, "http://127.0.0.1:9999", "localhost,127.0.0.1,::1",
                                  Path("/tmp/ca.pem"))
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["model"] == "opus", "existing settings were not preserved"
    assert data["env"]["HTTPS_PROXY"] == "http://127.0.0.1:9999"
    assert data["env"]["NODE_EXTRA_CA_CERTS"] == str(Path("/tmp/ca.pem"))
    assert backup.read_bytes() == original, "backup is not byte-exact"
    tapkit.unwire_settings(sp, backup)
    assert sp.read_bytes() == original, "restore is not byte-exact"
    assert not backup.exists()


@test
def ca_thumbprint(work):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2040, 1, 1))
            .sign(key, hashes.SHA256()))
    pem = work / "ca.pem"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    assert tapkit.thumbprint_pem(pem.read_bytes()) == cert.fingerprint(hashes.SHA1()).hex().upper()


@test
def analyzer_report(work):
    cap = fresh(work, "cap")
    os.environ.pop("CC_TAP_HOSTS", None)
    prefix = "20990101-0000"
    (cap / f"{prefix}-request.json").write_text(json.dumps({
        "model": "claude-opus-5-5", "max_tokens": 128000, "stream": True,
        "system": [{"type": "text", "text": "You are a test."}],
        "tools": [{"name": "Bash", "description": "x" * 500, "input_schema": {}}],
        "messages": [{"role": "user", "content": "hello"}]}), encoding="utf-8")
    (cap / f"{prefix}-response.sse.txt").write_text(
        'data: {"type":"message_start","message":{"usage":{"input_tokens":10}}}\n\n'
        'data: {"type":"message_delta","usage":{"output_tokens":42}}\n\n', encoding="utf-8")
    (cap / f"{prefix}-meta.json").write_text("{}", encoding="utf-8")
    (cap / "index.jsonl").write_text(
        json.dumps({"id": prefix, "path": "/v1/messages", "status": 200, "request_bytes": 900}) + "\n",
        encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPTS / "analyze.py"),
                           "--captures", str(cap), "--prefix", prefix],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for needle in ("system:", "tools:", "Bash", "usage", "messages:"):
        assert needle in proc.stdout, f"missing {needle!r} in:\n{proc.stdout}"


@test
def proxy_end_to_end(work):
    if importlib.util.find_spec("mitmproxy") is None:
        raise Skip("mitmproxy not importable; run with the skill venv python (see SKILL.md)")
    mitmdump = tapkit.find_mitmdump()
    if mitmdump is None:
        raise Skip("mitmdump executable not found")
    out = fresh(work, "e2e")
    confdir = work / "mitm-conf"
    proxy_port = tapkit.free_port()
    env = {**os.environ, "CC_TAP_OUT": str(out), "CC_TAP_HOSTS": "127.0.0.1,localhost"}
    logf = open(work / "mitmdump.log", "wb")
    proc = subprocess.Popen(
        [str(mitmdump), "--listen-host", "127.0.0.1", "--listen-port", str(proxy_port),
         "-s", str(SCRIPTS / "capture_addon.py"), "--set", f"confdir={confdir}",
         "--set", "termlog_verbosity=error", "--set", "ssl_insecure=true"],
        stdout=logf, stderr=subprocess.STDOUT, env=env)
    srv = srv2 = None
    try:
        assert tapkit.wait_port(proxy_port, 30), "proxy did not start (see mitmdump.log)"

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"hello-tap"
                self.send_response(200)
                self.send_header("content-type", "text/plain")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{proxy_port}"}))
        with opener.open(f"http://127.0.0.1:{srv.server_port}/plain", timeout=15) as r:
            assert r.read() == b"hello-tap"
        assert wait_for(lambda: index_has(out, "127.0.0.1", "/plain"), 10), "plain flow not captured"

        cert, key = make_cert(work, "localhost")
        srv2 = http.server.HTTPServer(("127.0.0.1", 0), H)
        sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sctx.load_cert_chain(str(cert), str(key))
        srv2.socket = sctx.wrap_socket(srv2.socket, server_side=True)
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        ca = confdir / "mitmproxy-ca-cert.pem"
        assert wait_for(ca.exists, 20), "mitmproxy CA not generated"
        client = ssl.create_default_context(cafile=str(ca))
        opener2 = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": f"http://127.0.0.1:{proxy_port}"}),
            urllib.request.HTTPSHandler(context=client))
        with opener2.open(f"https://localhost:{srv2.server_port}/secure", timeout=20) as r:
            assert r.read() == b"hello-tap"
        assert wait_for(lambda: index_has(out, "localhost", "/secure"), 10), "https flow not captured"
        meta = latest_meta(out, "/secure")
        assert meta["status"] == 200, meta
    finally:
        if srv:
            srv.shutdown()
        if srv2:
            srv2.shutdown()
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()


@test
def tap_on_off_lifecycle(work):
    if tapkit.venv_python() is None:
        raise Skip("skill venv missing; run scripts/setup_env.py first")
    assert not tapkit.STATE.exists(), "tap-state.json exists; a tap is on or state was left behind"
    settings = work / "lifecycle-settings.json"
    settings.write_text('{}\n', encoding="utf-8")
    original = settings.read_bytes()
    out = work / "life-out"
    confdir = work / "life-conf"
    port, web = tapkit.free_port(), tapkit.free_port()
    on = subprocess.run([sys.executable, str(SCRIPTS / "tap_on.py"), "--port", str(port),
                         "--web-port", str(web), "--out", str(out), "--settings", str(settings),
                         "--confdir", str(confdir)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    try:
        assert on.returncode == 0, on.stdout + on.stderr
        assert tapkit.port_open(port), "proxy not listening after tap_on"
        wired = json.loads(settings.read_text(encoding="utf-8"))
        assert wired["env"]["HTTPS_PROXY"] == f"http://127.0.0.1:{port}", wired
        assert tapkit.STATE.exists(), "tap-state.json not written"
        state = json.loads(tapkit.STATE.read_text(encoding="utf-8"))
        assert state["settings"] == str(settings) and state["ca_thumbprint"], state
    finally:
        off = subprocess.run([sys.executable, str(SCRIPTS / "tap_off.py")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert off.returncode == 0, off.stdout + off.stderr
    assert settings.read_bytes() == original, "settings not restored byte-exact"
    assert not tapkit.STATE.exists(), "tap-state.json not removed"
    assert wait_for(lambda: not tapkit.port_open(port), 10), f"port {port} still open after tap_off"


@test
def doctor_runs(work):
    proc = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py"), "--json"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert proc.returncode in (0, 1), proc.stderr
    checks = json.loads(proc.stdout)
    names = {c["name"] for c in checks}
    assert {"python", "skill venv", "mitmproxy", "settings wired"} <= names, names


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    work = Path(tempfile.mkdtemp(prefix="cc-tap-tests-"))
    print(f"workdir: {work}")
    addon_redacts_credentials(work)
    addon_tees_sse(work)
    addon_host_filter(work)
    settings_wiring_round_trip(work)
    ca_thumbprint(work)
    analyzer_report(work)
    proxy_end_to_end(work)
    tap_on_off_lifecycle(work)
    doctor_runs(work)
    counts = {s: sum(1 for _, st, _ in RESULTS if st == s) for s in ("PASS", "FAIL", "SKIP")}
    print(f"\nSUMMARY: {counts}")
    (work / "results.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    print(f"results: {work / 'results.json'}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
