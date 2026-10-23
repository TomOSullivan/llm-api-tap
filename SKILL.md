---
name: llm-api-tap
description: Capture and inspect the web traffic between Claude Code and its API on a machine you control, with credentials redacted. Sets up a loopback mitmproxy forward proxy wired through Claude Code's own settings (HTTPS_PROXY plus NODE_EXTRA_CA_CERTS), records requests, streamed responses and metadata to disk, produces a request-anatomy report (system blocks, tools, turns, token usage), and tears everything down cleanly by recorded thumbprint. Use whenever the user wants to see what Claude Code (desktop app or CLI) actually sends - comparing harnesses, debugging context composition, auditing prompts - or when installing this tap on another machine. Self-tests are sandboxed and touch nothing real.
---

# llm-api-tap

Observe what Claude Code sends to its API, on a machine you control. Original Second Wind
code (2026-10-22), no third-party content. Proven in a live session: about 97 exchanges
captured from the Claude desktop app, including full /v1/messages request bodies and SSE
streams.

## How it works, and why this way

- The Claude desktop app spawns native Claude Code child processes with ANTHROPIC_BASE_URL
  pinned to https://api.anthropic.com, so a base-URL override cannot work. What the
  children do honour is HTTPS_PROXY (and NODE_EXTRA_CA_CERTS) read from
  ~/.claude/settings.json.
- So: a loopback mitmproxy forward proxy; the settings env block pointed at it; the
  mitmproxy CA trusted via NODE_EXTRA_CA_CERTS (children also read the user certificate
  store, but the env var is explicit and portable).
- A mitmproxy addon writes each exchange to disk with authorization, x-api-key and cookie
  headers replaced by "[omitted]". Do not also enable mitmproxy's save_stream_file for
  captures that may be shared: the flow file stores full headers, tokens included.
- Only NEW Claude Code sessions pick up the settings; existing sessions keep their old
  environment.
- In the desktop app's Code tab, a "Blocked" session status means waiting for user input,
  not a failure.

## Requirements

- A machine you control. Windows fully tested; macOS/Linux work for proxy and capture,
  with manual CA steps.
- Python 3.10+, internet for the initial install (about 300 MB venv).

## Setup and self-test (fresh machine)

Run from the skill folder (Windows paths shown; use venv/bin/python elsewhere):

    python scripts/setup_env.py
    venv/Scripts/python.exe scripts/doctor.py
    venv/Scripts/python.exe tests/run_tests.py

The self-tests use ephemeral ports and temp directories only. They never touch real
~/.claude settings, the real ~/.mitmproxy CA, certificate stores, or Anthropic. They cover
credential redaction, SSE teeing, host filtering, settings wiring and exact restore, CA
thumbprinting, the analyzer, a plain-HTTP and an HTTPS round trip through a sandboxed
proxy with a throwaway CA, and a full tap_on/tap_off lifecycle. All must pass before
relying on or sharing the pack.

## Turning the tap on

    venv/Scripts/python.exe scripts/tap_on.py --install-ca

Defaults: proxy 127.0.0.1:8090, web UI http://127.0.0.1:8081 (loopback only), captures in
<skill>/captures, settings ~/.claude/settings.json (created if absent), CA in
~/.mitmproxy. Options: --port --web-port --no-web --out --settings --confdir --hosts.

tap_on.py backs up settings.json byte-for-byte (settings.json.tap-backup), wires the env
block while preserving your other settings, starts the proxy, waits for it and for the CA,
and records everything in tap-state.json. On Windows, --install-ca installs the CA into
the CURRENT USER store only; accept the Windows confirmation dialog if one appears.
Without --install-ca, run scripts/install_ca.py install separately.

Then start a NEW Claude Code session (desktop Code tab or CLI) and send a trivial prompt.
Verify:

    venv/Scripts/python.exe scripts/doctor.py
    type captures\index.jsonl     (Windows)

You should see POST entries for /v1/messages with status 200. If a new session cannot
connect, the CA is not trusted yet (run install_ca.py status).

## Reading the captures

    captures/PREFIX-meta.json          timing, status, headers (auth omitted)
    captures/PREFIX-request.json       full request body: system blocks, tools, messages
    captures/PREFIX-response.sse.txt   the raw streamed response
    venv/Scripts/python.exe scripts/analyze.py --latest

analyze.py prints the anatomy of the largest /v1/messages exchange: top-level sizes,
system prompt blocks, tools ranked by size, messages, thinking/effort settings, and token
usage parsed from the stream. Use --prefix P for a specific exchange, --captures DIR for
another directory.

## Turning the tap off

    venv/Scripts/python.exe scripts/tap_off.py --remove-ca

Restores settings.json byte-for-byte, stops the proxy, removes the CA by its recorded
thumbprint, deletes tap-state.json. Run this promptly when capture work ends: while the
CA is trusted, its private key (~/.mitmproxy) can mint certificates for any site for this
user account. If the proxy ever dies while settings still point at it, new Claude Code
sessions fail to connect; tap_off.py (or restoring the backup) fixes that.

## Safety

- Only on machines and clients you control. The CA trust is the real risk: user-store
  scope, short duration, remove by thumbprint.
- Captures contain conversation content and account identifiers even with headers
  redacted. Keep them local unless the owner agrees to share.
- Never paste raw flow files (save_stream_file output) into anything shared.

## Sharing

Copy or zip the skill folder without venv/, captures/, tap-state.json, any *.tap-backup and __pycache__ directories. The receiver runs Setup and self-test above. Provenance: original Second
Wind code, 2026-10-22.

## License

Copyright (c) 2026 Tom O'Sullivan. MIT License; see `LICENSE`. mitmproxy and its
dependencies are installed at setup time under their own licenses and are not
redistributed with this skill. See `README.md` for authorized-use and
non-affiliation notes.
