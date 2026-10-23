#!/usr/bin/env python
"""Anatomy report for a captured /v1/messages exchange (original Second Wind code).

Usage
  python analyze.py [--captures DIR] [--prefix P | --latest] [--out FILE]

--latest (default) picks the exchange with the largest request among /v1/messages flows
in index.jsonl. Prints top-level request sizes, system blocks, tools ranked by size,
messages, request settings, and token usage parsed from the SSE stream.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CAPTURES = Path(__file__).resolve().parents[1] / "captures"


def jlen(o):
    return len(json.dumps(o, ensure_ascii=False))


def preview(s, n=110):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "..."


def text_of(block):
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        if block.get("type") == "text":
            return block.get("text", "")
        return json.dumps(block, ensure_ascii=False)
    return str(block)


def pick_prefix(captures: Path, prefix):
    if prefix:
        return prefix
    idx = captures / "index.jsonl"
    if not idx.exists():
        raise SystemExit(f"no index.jsonl in {captures}")
    best, best_size = None, -1
    for line in idx.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("status") == 200 and "/v1/messages" in (e.get("path") or ""):
            if e.get("request_bytes", 0) > best_size:
                best, best_size = e.get("id"), e.get("request_bytes", 0)
    if not best:
        raise SystemExit("no /v1/messages exchange found in the index")
    return best


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--captures", default=str(DEFAULT_CAPTURES))
    ap.add_argument("--prefix")
    ap.add_argument("--out")
    a = ap.parse_args()
    captures = Path(a.captures)
    prefix = pick_prefix(captures, a.prefix)

    lines = []
    out = lines.append
    req_path = captures / f"{prefix}-request.json"
    if not req_path.exists():
        req_path = captures / f"{prefix}-request.txt"
    req = json.loads(req_path.read_text(encoding="utf-8"))
    out(f"# Request anatomy: {prefix}")
    out(f"total request JSON chars: {jlen(req):,}")
    out("top-level keys and sizes:")
    for k, v in sorted(req.items(), key=lambda kv: -jlen(kv[1])):
        out(f"  {k:<22} {jlen(v):>10,} chars"
            + ("" if isinstance(v, (list, dict)) and jlen(v) > 200 else f"  = {preview(json.dumps(v), 120)}"))

    sysb = req.get("system")
    if sysb is not None:
        blocks = sysb if isinstance(sysb, list) else [sysb]
        out(f"\n## system: {len(blocks)} block(s)")
        for i, b in enumerate(blocks):
            t = text_of(b)
            cc = b.get("cache_control") if isinstance(b, dict) else None
            out(f"  [{i}] {len(t):>8,} chars{'  cache_control=' + json.dumps(cc) if cc else ''}  :: {preview(t)}")

    tools = req.get("tools") or []
    out(f"\n## tools: {len(tools)} ({jlen(tools):,} chars total)")
    for t in sorted(tools, key=lambda t: -jlen(t))[:40]:
        out(f"  {jlen(t):>8,}  {t.get('name') or t.get('type')}  :: {preview(t.get('description', ''), 80)}")

    msgs = req.get("messages") or []
    out(f"\n## messages: {len(msgs)} ({jlen(msgs):,} chars)")
    for i, m in enumerate(msgs):
        c = m.get("content")
        parts = c if isinstance(c, list) else [c]
        first = next((text_of(p) for p in parts
                      if isinstance(p, str) or (isinstance(p, dict) and p.get("type") == "text")), "")
        out(f"  [{i}] {m.get('role'):<9} {jlen(c):>9,} chars  :: {preview(first, 90)}")

    for k in ("thinking", "max_tokens", "temperature", "context_management",
              "tool_choice", "effort", "output_config"):
        if k in req:
            out(f"\n{k}: {preview(json.dumps(req[k]), 300)}")

    sse = captures / f"{prefix}-response.sse.txt"
    if sse.exists():
        usage, stop, blocks = {}, None, {}
        for line in sse.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            t = ev.get("type")
            if t == "message_start":
                usage.update(ev.get("message", {}).get("usage", {}) or {})
            elif t == "message_delta":
                usage.update(ev.get("usage", {}) or {})
                stop = (ev.get("delta") or {}).get("stop_reason", stop)
            elif t == "content_block_start":
                bt = (ev.get("content_block") or {}).get("type")
                blocks[bt] = blocks.get(bt, 0) + 1
        out(f"\n## response usage: {json.dumps(usage)}")
        out(f"stop_reason: {stop}; content blocks: {blocks}")

    text = "\n".join(lines)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        print(f"\nWROTE {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
