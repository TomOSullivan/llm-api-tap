# Example: a synthetic capture

The files in `synthetic/` are a fully artificial sample of what this tap records. They exist so you can see the capture format and the analyzer's output without capturing anything yourself.

## Provenance

- The **structure** is modeled on a real captured session: four system blocks with cache-control breakpoints on the large ones, a tool list mixing core tools with `mcp__` server tools and one deferred stub, multi-block messages including a harness-injected trailing system message and one tool exchange, and a streamed response with thinking, signature, and text deltas around a ping.
- The **content** is entirely fictional. The agent ("Mesa"), its tools, the repository ("ledger-web"), the conversation, and every header value were written for this example. Nothing is copied from any real prompt, product, or session. The model name and API field names are illustrative of the wire format this tap observes.
- The `Authorization` header in the meta file shows the redaction applied to every real capture.

## Regenerating

    python examples/generate_example.py
    venv/Scripts/python.exe scripts/analyze.py --captures examples/synthetic --out examples/synthetic/anatomy-report.txt

(`venv/bin/python` on macOS/Linux.) `anatomy-report.txt` is committed for reference; regenerate it after changing the generator.
