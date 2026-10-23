#!/usr/bin/env python
"""Generate the synthetic example capture in examples/synthetic/.

Everything here is fiction, written for this example: the "Mesa" agent, its
tools, the "ledger-web" repository, the conversation, and all header values.
The structure mirrors a real captured session (system block count and cache
breakpoints, tool-list shape, message sequence, SSE event grammar) but no real
prompt, product, or account text is reproduced. Deterministic; writes only
into examples/synthetic/.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).resolve().parent / "synthetic"
PREFIX = "20260101-091500-0001"
MODEL = "claude-opus-5-5"

SYSTEM_0 = (
    "You are Mesa, a coding agent working in the user's terminal. You read and "
    "edit files, run commands, and explain your work as you go. Prefer the "
    "smallest change that solves the stated problem, and verify what you change."
)

SYSTEM_1 = (
    "Environment: linux x86_64, bash 5.2, Node 22. Workspace: "
    "/home/dev/ledger-web, branch fix/txn-pagination."
)

SYSTEM_2 = """# Tool rules

Tools exist to serve the task, not to perform diligence. Think first, then call with intent.

Reading and editing
- Read a file before editing it, and read enough context around the target lines. An edit made against memory instead of the file is a bug waiting to happen.
- Use edit_file for surgical changes to a file you have read. Use write_file only for new files or full rewrites you can justify.
- When a file is large, read it in windows with offset and limit instead of pulling it whole.

Commands
- run_command executes in the workspace root with the user's environment. The default timeout is 120 seconds; pass run_in_background for servers, watchers, and anything that does not terminate on its own.
- Read the full output before drawing conclusions. Truncated output is a signal to narrow the command, not to guess at the missing part.
- Ask before running anything that deletes data, rewrites history, installs system-level packages, or reaches outside the workspace.

Search
- search_code is the first move when you know a symbol, string, or pattern but not a location. It honors ignore files.
- list_directory for orientation; search_code for targeting; read_file for truth.

Questions and plans
- Ask a question only when the answer changes what you would do. Scope, risk, and intent are worth asking about; facts in the workspace are not.
- Keep the task plan current. Update it when a step completes, not in a batch at the end.

Parallelism
- Independent read-only calls may run together. Anything that writes runs alone, in order."""

SYSTEM_3 = """# Mesa operating manual

## The working loop

Move through four phases and do not skip ahead.

Understand. Reproduce the problem before explaining it. Read the code the problem lives in, and the code that calls it. A theory formed before reproduction is a guess wearing a lab coat.

Plan. State the approach in a sentence or two before acting. If the plan exceeds three steps, put it in the task plan. Change the plan when the evidence changes, and say so when you do.

Act. Make the smallest set of changes that satisfies the task. One logical change per edit, each defensible on its own.

Verify. Run the narrow test first, then the wider suite. Report what ran and what did not. A change you have not verified is a proposal, not a fix.

## Editing code

- Match the file's existing style: indentation, quotes, naming, comment tone. Consistency with neighbors beats personal preference.
- No drive-by refactors. If something adjacent is wrong, note it and leave it, unless the task is that thing.
- Keep imports, types, and call sites moving together. Half of a rename is worse than none.
- If your change makes a comment or docstring wrong, fix the comment in the same edit.
- Preserve the diff's readability: a reviewer should be able to read the change once and know what it does and why.

## Tests

- A bug fix ships with a regression test that fails without the fix. If you cannot write one, you do not understand the bug yet.
- Never weaken an assertion, narrow a fixture, or delete a test to make a suite pass. If a test is genuinely wrong, say so and make the case.
- Run the touched tests first; run the full suite before declaring done. If the full suite is too slow to run, run the targeted subset and say exactly what was not run.
- Prefer tests that describe behavior over tests that mirror implementation.

## Commands

- Long-running processes belong in the background. Poll their output; do not block on them blindly.
- A non-zero exit code is information. Read the output before deciding it is noise.
- Destructive commands, force operations, and package installs need explicit user confirmation. This is not negotiable and not a formality.

## Communication

- Lead with the answer, then the evidence, then the caveats.
- Show the decisive diff, not every diff. Summarize what you checked in a line or two.
- Say what you verified, what you did not, and what you are unsure about. Three separate lists, kept honest.
- If you disagree with the user's approach, say so once, with reasons, and then do what they decide.

## Uncertainty

- Separate what you read from what you inferred from what you assumed. Label them when it matters.
- Guesses are allowed; presenting guesses as findings is not. Say what would confirm or refute each one.
- Never report a test as passing unless you saw it pass in this session.

## Context discipline

- Large files are read in windows. Re-read what matters rather than trusting a summary of it.
- When you drop old detail to save room, note what you dropped.
- The workspace briefing is authoritative for layout and conventions; code read this session is authoritative for behavior. When they conflict, the code wins and the briefing gets corrected."""

WORKSPACE = """# Workspace briefing: ledger-web

ledger-web is a small double-entry bookkeeping service: a Fastify HTTP layer over PostgreSQL, written in strict TypeScript. Three people work on it, and all three read every PR.

## Layout

- src/server.ts - entrypoint; plugin and route registration
- src/routes/transactions.ts - GET/POST /api/transactions, the listing and creation endpoints
- src/routes/accounts.ts - account CRUD
- src/db/queries.ts - all hand-written SQL, built through src/db/qb.ts
- src/db/qb.ts - the query builder: select, where, orderBy, limit, offset; nothing clever
- src/domain/ledger.ts - posting rules and balance invariants
- src/validation/schemas.ts - zod schemas; every route validates before touching the database
- tests/transactions.test.ts, tests/accounts.test.ts - vitest suites
- tests/fixtures/loader.ts - starts a throwaway Postgres container and seeds it per suite

## Conventions

- Two-space indent, double quotes, semicolons.
- Errors are thrown as AppError subclasses; routes never build error responses inline.
- SQL lives in queries.ts only. Routes pass structured options, never SQL fragments.
- Route handlers stay under roughly 80 lines; anything longer moves to the domain layer.

## The failure

vitest run tests/transactions.test.ts ends with:

  x GET /api/transactions returns page 3 after 60 seeded transactions (14 ms)
    expected 20 items, received 1

The suite was green before commit 4f2c1e8 ("Cap default page size at 50"). That commit touched src/routes/transactions.ts and src/validation/schemas.ts.

## Facts worth knowing

- src/db/qb.ts defaults offset to 0; nothing in the route currently passes an offset.
- The fixture loader seeds 60 transactions for this test, many sharing a posted_at timestamp.
- GET /api/transactions has one consumer today: the internal review dashboard, which walks pages in order."""

TASK = """# Task

Fix the pagination defect in GET /api/transactions.

1. Reproduce the failure from the current checkout.
2. Identify the root cause; expect it in how the route threads the page parameter.
3. Apply the smallest correct fix.
4. Add a regression test that fails without the fix.
5. Run the full suite and report.

Acceptance criteria:

- GET /api/transactions?page=3 and limit=20 returns items 41 through 60, ordered by posted_at descending with a deterministic tiebreaker.
- Omitting page behaves as page=1.
- page=0 or a negative page returns a 422 from the existing validation schema, not a 500.
- No public API shape changes."""

NOTES = """# Constraints

- The staging database is shared with the demo team. Never point the app or the tests at staging; tests use the fixture loader only.
- The maintainer is away until Thursday. Anything you decide alone gets a note in the PR description.
- Keep the change reviewable in one sitting: if the fix wants to grow, stop and say what it wants to become.
- Do not upgrade dependencies while fixing this."""

TINY = "Begin"

SYSTEM_MSG = """## Session context, refreshed by the harness

- Time: 2026-01-01T14:15:02Z
- Branch fix/txn-pagination, working tree clean
- Open files: src/routes/transactions.ts (around line 84), src/db/queries.ts (line 210), src/db/qb.ts (line 67)
- Task plan: 3 of 5 steps complete. Current step: identify the root cause. Remaining: apply the fix, add the regression test.
- Recent commands: vitest run tests/transactions.test.ts (exit 1), git log --oneline -5 (exit 0), git diff --stat (clean)

### Standing reminders

- The workspace briefing at the top of this conversation is the source of truth for layout and conventions. Code read this session overrides it where they disagree.
- Update the task plan when a step completes, before starting the next one.
- Commands producing more than a few hundred lines should be summarized, not pasted.
- The context budget for this session is 180k tokens; roughly 61k are in use. Large reads should use windows.
- When you believe the fix is ready, run the narrow test, then the full suite, then report with a diff summary and what you verified."""

THINKING_REQ = """Two suspects: the route never forwards page to the query, or the builder drops the offset it is given. The briefing notes that qb.offset defaults to 0 and that the route passes no offset, which would make every request return the first page - but the test saw one item, not twenty, so something else is interacting with the ordering. The seed data shares posted_at timestamps across many rows, and if the ORDER BY has no tiebreaker, rows can shift between identical pages. Search for where page is parsed and where limit and offset are computed, then read the route around the call site before theorizing further."""

TOOL_RESULT = """src/routes/transactions.ts
  38:  const query = ListTransactionsSchema.parse(req.query);
  84:  const rows = await listTransactions({ accountId, limit: query.limit });
src/db/queries.ts
 210: export async function listTransactions(opts: { accountId: string; limit: number; offset?: number }) {
 216:    .offset(opts.offset ?? 0)
src/validation/schemas.ts
  72:  limit: z.coerce.number().int().min(1).max(50).default(20),
  73:  page: z.coerce.number().int().min(1).default(1),

3 files, 6 matches for 'page' (14 matches in tests/ suppressed)"""

THINKING_RESP = (
    "Confirmed: the schema parses page at schemas.ts:73 but the route never forwards "
    "it, so the query always runs with offset 0. The single-item result is explained "
    "by the missing ordering tiebreaker: shared posted_at values make the result set "
    "unstable once any limit interacts with it. The fix threads page through "
    "listTransactions, computes offset as (page - 1) times limit, and adds a "
    "deterministic tiebreaker to the ORDER BY. The regression test then pins "
    "pagination and determinism together."
)

RESPONSE_TEXT = """Found it. Two defects are stacked on top of each other.

1. The route drops page. src/routes/transactions.ts:84 calls listTransactions with limit only. page is parsed by the schema and then ignored, so every request runs with offset 0 and returns the first page.

2. The ordering has no tiebreaker. The fixture seeds many transactions with the same posted_at, and the query orders by posted_at alone, so rows repeat and vanish across pages even once paging works. That instability is why the test saw one item instead of twenty.

Planned fix, the smallest that meets the acceptance criteria:

- src/routes/transactions.ts: pass offset: (query.page - 1) * query.limit into listTransactions.
- src/db/queries.ts: add id DESC as a tiebreaker to the ORDER BY in listTransactions.
- tests/transactions.test.ts: a regression test that seeds 60 rows with shared timestamps and asserts that pages 1 through 3 partition the set exactly, and that page=0 returns a 422 from the existing validation.

Applying the edits next."""

SIGNATURE = ("Eo8BCkgIARIBGAIiQmV4YW1wbGUtc2lnbmF0dXJlLWRhdGEtZm9yLXRoZS1s"
             "bG0tYXBpLXRhcC1leGFtcGxlLTlpZDAxMjM0NTY3OA==")

TOOLS = [
    {
        "name": "run_command",
        "description": (
            "Runs a shell command in the workspace root with the user's environment. "
            "The default timeout is 120 seconds; anything that keeps running (servers, "
            "watchers, tail) must set run_in_background. Output above 20000 characters "
            "is truncated with a marker; narrow the command instead of guessing at the "
            "missing part. Commands that delete data, rewrite git history, install "
            "system packages, or reach outside the workspace require explicit user "
            "confirmation first, with no exceptions and no abbreviations."),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command line to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
                "run_in_background": {"type": "boolean", "description": "Run without waiting"},
                "description": {"type": "string", "description": "What this command is for"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "spawn_subtask",
        "description": (
            "Starts an isolated sub-agent with a fresh context window to investigate a "
            "bounded question and return a written summary. The sub-agent shares the "
            "workspace but not this conversation. Use it for searches or log sweeps "
            "that would flood your own context with results you only need in aggregate. "
            "Give it the question, the boundaries, and what a useful answer looks "
            "like; do not use it for decisions."),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The bounded question to investigate"},
                "focus": {"type": "string", "description": "Paths or areas to look at"},
                "budget": {"type": "integer", "description": "Approximate token budget"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Reads a file from the workspace and returns its contents with line "
            "numbers. Use offset and limit to read large files in windows instead of "
            "loading them whole. Binary files return a bounded preview with a note "
            "recommending a dedicated tool."),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Workspace-relative or absolute path"},
                "offset": {"type": "integer", "description": "First line to return, 1-based"},
                "limit": {"type": "integer", "description": "Maximum lines to return"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Applies an exact string replacement in a file. old_string must occur "
            "exactly once unless replace_all is set. The call fails rather than "
            "guessing when the match is ambiguous or absent, and it never edits a "
            "file you have not read this session."),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string", "description": "Exact text to replace"},
                "new_string": {"type": "string", "description": "Replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace every occurrence"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "update_task_plan",
        "description": (
            "Replaces the current task plan. The plan is a short ordered list of steps "
            "with a done flag; keep steps concrete enough that finishing one is "
            "unambiguous. Update it when a step completes rather than in a batch at "
            "the end, and revise it when the approach changes."),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "done": {"type": "boolean"},
                        },
                        "required": ["step", "done"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Searches workspace files for a regular expression and returns matching "
            "lines with paths and line numbers. Honors ignore files. Use context to "
            "include surrounding lines and max_results to bound the output."),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression"},
                "glob": {"type": "string", "description": "File glob to restrict the search"},
                "context": {"type": "integer", "description": "Context lines around matches"},
                "max_results": {"type": "integer"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Writes content to a file, creating parent directories as needed. "
            "Overwrites the file if it exists. Use only for new files or full "
            "rewrites; for changes to a file you have read, prefer edit_file."),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "ask_user_question",
        "description": (
            "Presents one or more questions to the user with optional multiple-choice "
            "answers. Use only when the answer changes what you would do next: scope, "
            "risk appetite, or intent. Facts that can be read from the workspace are "
            "not questions."),
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["question"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Retrieves an HTTP or HTTPS URL and returns the body as text, converting "
            "HTML to readable text when possible. Never place credentials in the URL. "
            "Responses above max_chars are truncated with a marker."),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_directory",
        "description": (
            "Lists one level of a directory with names, types, and sizes. Use it for "
            "orientation; use search_code once you know what you are looking for."),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "mcp__builds__get_status",
        "description": "Returns the status of the most recent CI build for a branch.",
        "input_schema": {
            "type": "object",
            "properties": {"branch": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "mcp__builds__tail_logs",
        "description": "Returns the last N lines of a CI build log.",
        "input_schema": {
            "type": "object",
            "properties": {"lines": {"type": "integer"}, "job": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "mcp__browser__navigate",
        "description": "Opens a URL in the headless browser and returns the page title and final URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "mcp__browser__read_page",
        "description": "Returns the readable text of the current browser page, truncated to max_chars.",
        "input_schema": {
            "type": "object",
            "properties": {"max_chars": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "deferred_tool_slot",
        "description": "",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def split_words(text, n):
    words = text.split(" ")
    if len(words) <= n:
        return [text]
    size = max(1, round(len(words) / n))
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def build_request():
    return {
        "model": MODEL,
        "max_tokens": 128000,
        "stream": True,
        "metadata": {"user_id": "user_mesa_example_7f3a2b"},
        "thinking": {"type": "enabled", "display": "condensed"},
        "output_config": {"effort": "high"},
        "context_management": {
            "edits": [
                {"type": "clear_tool_uses", "keep": "last",
                 "trigger": {"input_tokens": 80000}},
            ]
        },
        "system": [
            {"type": "text", "text": SYSTEM_0},
            {"type": "text", "text": SYSTEM_1},
            {"type": "text", "text": SYSTEM_2,
             "cache_control": {"type": "ephemeral", "ttl": "1h"}},
            {"type": "text", "text": SYSTEM_3,
             "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        ],
        "tools": TOOLS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": WORKSPACE},
                    {"type": "text", "text": TASK},
                    {"type": "text", "text": NOTES},
                    {"type": "text", "text": TINY},
                ],
            },
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_MSG}],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": THINKING_REQ, "signature": SIGNATURE},
                    {"type": "tool_use", "id": "toolu_01Example", "name": "search_code",
                     "input": {"pattern": "page", "glob": "src/**/*.ts", "context": 3}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_01Example",
                     "content": TOOL_RESULT},
                ],
            },
        ],
    }


def build_sse():
    ev = []

    def add(name, obj):
        ev.append(f"event: {name}\ndata: {json.dumps(obj, ensure_ascii=False)}")

    start_usage = {
        "input_tokens": 3,
        "cache_creation_input_tokens": 14196,
        "cache_read_input_tokens": 37748,
        "output_tokens": 9,
        "cache_creation": {"ephemeral_5m_input_tokens": 0,
                           "ephemeral_1h_input_tokens": 14196},
        "service_tier": "standard",
    }
    add("message_start", {"type": "message_start", "message": {
        "id": "msg_example_01ABC", "type": "message", "role": "assistant",
        "model": MODEL, "content": [], "stop_reason": None,
        "stop_sequence": None, "usage": start_usage}})
    add("content_block_start", {"type": "content_block_start", "index": 0,
                                "content_block": {"type": "thinking", "thinking": ""}})
    add("ping", {"type": "ping"})
    for chunk in split_words(THINKING_RESP, 2):
        add("content_block_delta", {"type": "content_block_delta", "index": 0,
                                    "delta": {"type": "thinking_delta", "thinking": chunk}})
    add("content_block_delta", {"type": "content_block_delta", "index": 0,
                                "delta": {"type": "signature_delta", "signature": SIGNATURE}})
    add("content_block_stop", {"type": "content_block_stop", "index": 0})
    add("content_block_start", {"type": "content_block_start", "index": 1,
                                "content_block": {"type": "text", "text": ""}})
    for chunk in split_words(RESPONSE_TEXT, 20):
        add("content_block_delta", {"type": "content_block_delta", "index": 1,
                                    "delta": {"type": "text_delta", "text": chunk}})
    add("content_block_stop", {"type": "content_block_stop", "index": 1})
    final_usage = dict(start_usage)
    final_usage.update({
        "output_tokens": 287,
        "output_tokens_details": {"thinking_tokens": 91},
        "iterations": [{
            "type": "message", "input_tokens": 3, "output_tokens": 287,
            "cache_read_input_tokens": 37748,
            "cache_creation_input_tokens": 14196,
            "cache_creation": {"ephemeral_5m_input_tokens": 0,
                               "ephemeral_1h_input_tokens": 14196},
        }],
    })
    add("message_delta", {"type": "message_delta",
                          "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                          "usage": final_usage})
    add("message_stop", {"type": "message_stop"})
    return "\n".join(ev) + "\n"


def build_meta(nbytes):
    return {
        "id": PREFIX,
        "utc": "2026-01-01T14:14:58Z",
        "method": "POST",
        "host": "api.anthropic.com",
        "path": "/v1/messages?beta=true",
        "status": 200,
        "model": MODEL,
        "streamed": True,
        "request_bytes": nbytes,
        "duration_s": 4.212,
        "error": None,
        "request_headers": {
            "Accept": "application/json",
            "Authorization": "[omitted]",
            "Content-Type": "application/json",
            "User-Agent": "mesa-agent/0.9.2 (linux; x86_64) node/22",
            "anthropic-beta": "context-management-2025-08-07",
            "anthropic-version": "2023-06-01",
            "x-client-request-id": "b1f2e3d4-0a5b-4c6d-8e7f-90a1b2c3d4e5",
        },
        "response_headers": {
            "Content-Type": "text/event-stream",
            "Date": "Thu, 01 Jan 2026 14:15:02 GMT",
            "request-id": "req_example_01D2800XTFHZQBW",
            "strict-transport-security": "max-age=31536000",
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    req = build_request()
    req_text = json.dumps(req, indent=2, ensure_ascii=False)
    (OUT / f"{PREFIX}-request.json").write_text(req_text, encoding="utf-8", newline="\n")
    sse = build_sse()
    (OUT / f"{PREFIX}-response.sse.txt").write_text(sse, encoding="utf-8", newline="\n")
    nbytes = len(json.dumps(req, ensure_ascii=False).encode("utf-8"))
    meta = build_meta(nbytes)
    (OUT / f"{PREFIX}-meta.json").write_text(json.dumps(meta, indent=2),
                                             encoding="utf-8", newline="\n")
    entry = {k: meta[k] for k in ("id", "utc", "method", "host", "path", "status",
                                  "model", "streamed", "request_bytes", "duration_s",
                                  "error")}
    (OUT / "index.jsonl").write_text(json.dumps(entry) + "\n",
                                     encoding="utf-8", newline="\n")

    assert len(req["system"]) == 4
    assert len(req["tools"]) == 15
    assert len(req["messages"]) == 4
    deltas = sse.count("text_delta")
    assert 15 <= deltas <= 30, deltas

    print(f"WROTE {OUT / (PREFIX + '-request.json')} ({len(req_text)} chars)")
    print(f"WROTE {OUT / (PREFIX + '-response.sse.txt')} ({len(sse)} chars)")
    print(f"WROTE {OUT / (PREFIX + '-meta.json')}")
    print(f"WROTE {OUT / 'index.jsonl'}")
    print(f"shape: system=4 blocks, tools=15, messages=4, "
          f"request_bytes={nbytes}, text_deltas={deltas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
