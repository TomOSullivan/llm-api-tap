"""mitmproxy addon: capture Claude Code API traffic with credentials redacted.

Original Second Wind code. Runs inside mitmproxy/mitmweb/mitmdump via -s. Writes, per
captured exchange (prefix RUN-NNNN, RUN unique per proxy process):

  PREFIX-request.json       request body, pretty-printed when it parses as JSON
  PREFIX-request.txt        request body when it is not JSON
  PREFIX-response.sse.txt   streamed SSE response body (teed live; client keeps streaming)
  PREFIX-response.txt       non-streamed response body
  PREFIX-meta.json          method, host, path, status, model, timing, headers
  index.jsonl               one JSON summary line per exchange

Credential hygiene: authorization, x-api-key, cookie, set-cookie and proxy-authorization
headers are replaced with "[omitted]" in meta files. Do not additionally enable
mitmproxy's save_stream_file when captures may be shared: the flow file stores full
headers, tokens included.

Environment (read at runtime):
  CC_TAP_OUT    output directory (default: captures)
  CC_TAP_HOSTS  comma-separated host suffixes to capture (default: .anthropic.com,claude.ai)
"""
import json
import os
import threading
import time
from pathlib import Path

SECRET_HEADERS = {"authorization", "x-api-key", "cookie", "set-cookie", "proxy-authorization"}
_lock = threading.Lock()
_counter = 0
RUN = time.strftime("%Y%m%d-%H%M%S")


def _out():
    path = Path(os.environ.get("CC_TAP_OUT", "captures"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _host_rules():
    raw = os.environ.get("CC_TAP_HOSTS", ".anthropic.com,claude.ai")
    return [h.strip().lower().lstrip(".") for h in raw.split(",") if h.strip()]


def _wanted(host):
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in _host_rules())


def _next_id():
    global _counter
    with _lock:
        _counter += 1
        return _counter


def _prefix(flow):
    return f"{RUN}-{flow.metadata.get('cap_id', 0):04d}"


def _safe_headers(headers):
    out = {}
    for k, v in headers.items(multi=True):
        out[k] = "[omitted]" if k.lower() in SECRET_HEADERS else v
    return out


def request(flow):
    if not _wanted(flow.request.pretty_host):
        flow.metadata["cap_skip"] = True
        return
    flow.request.headers.pop("accept-encoding", None)  # readable tees
    flow.metadata["cap_id"] = _next_id()
    flow.metadata["cap_t0"] = time.time()


def responseheaders(flow):
    if flow.metadata.get("cap_skip"):
        return
    ctype = flow.response.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        fh = open(_out() / f"{_prefix(flow)}-response.sse.txt", "wb")
        flow.metadata["cap_sse"] = fh

        def tee(data):
            if data:
                fh.write(data)
                fh.flush()
            return data

        flow.response.stream = tee


def response(flow):
    _write(flow)


def error(flow):
    _write(flow)


def _write(flow):
    if flow.metadata.get("cap_skip") or flow.metadata.get("cap_written"):
        return
    flow.metadata["cap_written"] = True
    prefix = _prefix(flow)

    streamed = False
    fh = flow.metadata.pop("cap_sse", None)
    if fh is not None:
        streamed = True
        try:
            fh.close()
        except Exception:
            pass

    model = None
    req_text = flow.request.get_text(strict=False) or ""
    if req_text:
        try:
            body = json.loads(req_text)
            model = body.get("model") if isinstance(body, dict) else None
            (_out() / f"{prefix}-request.json").write_text(
                json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            (_out() / f"{prefix}-request.txt").write_text(req_text, encoding="utf-8")

    if flow.response is not None and not streamed:
        resp_text = flow.response.get_text(strict=False)
        if resp_text:
            (_out() / f"{prefix}-response.txt").write_text(resp_text, encoding="utf-8")

    t0 = flow.metadata.get("cap_t0", time.time())
    meta = {
        "id": prefix,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "method": flow.request.method,
        "host": flow.request.pretty_host,
        "path": flow.request.path,
        "status": flow.response.status_code if flow.response is not None else None,
        "model": model,
        "streamed": streamed,
        "request_bytes": len(flow.request.raw_content or b""),
        "duration_s": round(time.time() - t0, 3),
        "error": str(flow.error) if flow.error else None,
        "request_headers": _safe_headers(flow.request.headers),
        "response_headers": _safe_headers(flow.response.headers) if flow.response is not None else None,
    }
    (_out() / f"{prefix}-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    summary = {k: meta[k] for k in ("id", "utc", "method", "host", "path", "status", "model",
                                    "streamed", "request_bytes", "duration_s", "error")}
    with _lock:
        with open(_out() / "index.jsonl", "a", encoding="utf-8") as idx:
            idx.write(json.dumps(summary) + "\n")
