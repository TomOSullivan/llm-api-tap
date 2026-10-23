# llm-api-tap

Capture and inspect the web traffic between Claude Code and its API on a machine you
control, with credentials redacted. Proven in a live session: about 97 exchanges
captured from the Claude desktop app, including full `/v1/messages` request bodies and
SSE streams.

## How it works

The Claude desktop app spawns native Claude Code child processes with
`ANTHROPIC_BASE_URL` pinned to `https://api.anthropic.com`, so a base-URL override
cannot win. What the child processes do honour is `HTTPS_PROXY` and
`NODE_EXTRA_CA_CERTS` read from `~/.claude/settings.json`. This tool wires those
settings to a loopback [mitmproxy](https://mitmproxy.org/) forward proxy, records every
exchange (request body, streamed response, metadata) to disk with authorization headers
replaced by `[omitted]`, and restores your settings when you are done.

Use it to see what a harness actually sends: system prompt blocks, tool definitions,
turn structure, thinking and effort settings, token usage. Good for comparing harnesses,
debugging context composition, and auditing prompts.

## Authorized use only

This tool is for observing software on machines and accounts **you own or are
explicitly authorized to monitor**. Captures contain conversation content and account
identifiers. Running it against systems, accounts, or networks you are not authorized
to inspect may violate law, contract, or both. If you are not sure you are authorized,
do not use it.

## No affiliation

This is an independent tool. It is not affiliated with, endorsed by, or sponsored by
Anthropic PBC. "Claude" and "Claude Code" are trademarks of Anthropic PBC, used here
only to describe what the tool works with. This project is also not part of the
mitmproxy project; mitmproxy is a third-party dependency.

## Requirements

- Windows is fully tested; macOS and Linux work for the proxy and capture with manual
  CA installation steps.
- Python 3.10+ and internet access for the initial install (about 300 MB venv).

## Setup and self-test

From the project root:

    python scripts/setup_env.py
    venv/Scripts/python.exe scripts/doctor.py
    venv/Scripts/python.exe tests/run_tests.py

(`venv/bin/python` on macOS/Linux.) The self-tests use ephemeral ports and temporary
directories only. They never touch your real `~/.claude` settings, the real
`~/.mitmproxy` CA, your certificate stores, or Anthropic. All tests must pass before
you rely on the tool.

## Turning the tap on

    venv/Scripts/python.exe scripts/tap_on.py --install-ca

Defaults: proxy `127.0.0.1:8090`, web UI `http://127.0.0.1:8081` (loopback only),
captures in `captures/`, settings `~/.claude/settings.json` (created if absent), CA in
`~/.mitmproxy`. Options: `--port --web-port --no-web --out --settings --confdir
--hosts`.

`tap_on.py` backs up `settings.json` byte-for-byte as `settings.json.tap-backup`, wires
the env block while preserving your other settings, starts the proxy, waits for it and
for the CA, and records everything in `tap-state.json`. On Windows, `--install-ca`
installs the CA into the current user's certificate store only; accept the Windows
confirmation dialog if one appears.

Then start a NEW Claude Code session (desktop Code tab or CLI; existing sessions keep
their old environment) and send a trivial prompt. Verify with
`venv/Scripts/python.exe scripts/doctor.py` and look for `POST` entries for
`/v1/messages` with status 200 in `captures/index.jsonl`. If a new session cannot
connect, the CA is not trusted yet.

## Reading the captures

    captures/PREFIX-meta.json          timing, status, headers (auth omitted)
    captures/PREFIX-request.json       full request body: system blocks, tools, messages
    captures/PREFIX-response.sse.txt   the raw streamed response

    venv/Scripts/python.exe scripts/analyze.py --latest

`analyze.py` prints the anatomy of the largest `/v1/messages` exchange: top-level
sizes, system prompt blocks, tools ranked by size, messages, thinking/effort settings,
and token usage parsed from the stream. Use `--prefix P` for a specific exchange and
`--captures DIR` for another directory.

## Example

`examples/synthetic/` holds a fully artificial sample capture: the same structure as a
real session (four system blocks with cache-control breakpoints, a mixed tool list, a
tool exchange, a streamed response with thinking and text deltas) with entirely
fictional content. `examples/synthetic/anatomy-report.txt` shows what `analyze.py`
produces from it. See `examples/README.md` for provenance and regeneration.

## Turning the tap off

    venv/Scripts/python.exe scripts/tap_off.py --remove-ca

This restores `settings.json` byte-for-byte, stops the proxy, removes the CA by its
recorded thumbprint, and deletes `tap-state.json`. Run it promptly when capture work
ends: while the CA is trusted, its private key (`~/.mitmproxy`) can mint certificates
for any site for this user account. If the proxy ever dies while settings still point
at it, new Claude Code sessions fail to connect; `tap_off.py` (or restoring the backup)
fixes that.

## Privacy and safety notes

- Authorization headers (`authorization`, `x-api-key`, `cookie`) are replaced with
  `[omitted]` in saved captures. Captures still contain conversation content and
  account identifiers; keep them local unless everyone involved agrees to share.
- Do not enable mitmproxy's `save_stream_file` for captures that may be shared: flow
  files store full headers, tokens included.
- In the desktop app's Code tab, a "Blocked" session status means waiting for user
  input, not a failure.
- `SKILL.md` is the agent-facing manifest for skill loaders; this README covers human
  use.

## License

Copyright (c) 2026 Tom O'Sullivan. Released under the [MIT License](LICENSE).

All code in this repository is original. mitmproxy and its dependencies are installed
at setup time under their own licenses and are not redistributed here.
