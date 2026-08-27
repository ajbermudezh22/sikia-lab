# sikia-lab

A working lab for real-time medical documentation infrastructure: streaming audio in,
structured clinical text out, with the provider layer treated as unreliable by default.

Two things live here:

1. `src/sikia_lab/` — a small but real implementation of the pieces that matter:
   a WebSocket audio pipeline, a health-aware multi-provider router, and an
   offline LLM-as-judge eval harness.
2. `workspace/` — scratch space for reading *other* codebases (gitignored). See
   "Reading an unfamiliar codebase" below.

## Working agreements

**Ship the vertical slice.** Prefer one path that works end-to-end over four
half-built layers. If a piece has to be faked to keep the slice moving, fake it
behind the real interface and leave a `# FAKE:` marker so it is greppable.

**Failure is the normal case.** Every provider call is assumed to time out, return
garbage, or rate-limit. Code that only handles the happy path is not finished. New
provider integrations need a timeout, a fallback, and a test that kills the primary.

**Measure before optimizing.** Latency and cost claims need a number from
`scripts/bench.py` or an eval run, not intuition.

**Tests are the demo.** `pytest` must stay green. A test that reproduces the bug
comes before the fix.

**Don't guess at medical semantics.** If a transcription or summarization decision
depends on clinical meaning, flag it for a human rather than inventing a rule.
Wrong confidence in this domain is worse than a gap.

## Layout

| Path | What's in it |
|---|---|
| `src/sikia_lab/transport.py` | FastAPI app, WebSocket audio ingest, session lifecycle |
| `src/sikia_lab/router.py` | Health-aware provider selection, failover, circuit breaking |
| `src/sikia_lab/providers/` | STT + LLM provider adapters behind one protocol |
| `src/sikia_lab/eval/` | LLM-as-judge harness, rubrics, scoring |
| `tests/` | pytest; `test_router.py` is the interesting one |
| `scripts/` | bootstrap, bench, Cloud Run deploy |
| `notes/` | Local working notes (gitignored) |

## Commands

```bash
uv sync                      # install (Python 3.12)
uv run pytest -q             # tests
uv run uvicorn sikia_lab.transport:app --reload   # dev server on :8000
uv run python scripts/bench.py                    # latency/cost numbers
./scripts/deploy_cloudrun.sh                      # build + deploy to Cloud Run
```

Providers run in `fake` mode unless real keys are present, so the whole thing runs
and tests green with no credentials. `SIKIA_PROVIDER_MODE=live` switches over.

## Reading an unfamiliar codebase

When a repo is cloned into `workspace/<name>/`, work it in this order and write
findings to `notes/findings-<name>.md` as you go — not at the end.

1. **Shape before detail.** Entry points, dependency manifest, CI config, test
   layout. Where does a request enter and where does it leave?
2. **Follow one request end-to-end.** Pick the most important path and trace it
   through every hop. This surfaces more than any amount of breadth-first reading.
3. **Read the tests for intent.** Tests say what the authors were afraid of.
4. **Find the seams.** Where does this system talk to something it doesn't control?
   Those are where the bugs and the improvement opportunities are.
5. **Separate observation from recommendation.** A finding states what the code
   does and why it matters. A recommendation is a separate, clearly-labeled claim.

Cite everything as `path/to/file.py:123`. A finding without a line reference is a
guess and should be labeled as one.

## Style

- Python 3.12, `ruff` for lint/format, type hints on anything crossing a module
  boundary. Not a religion — untyped is fine inside a function.
- Structured logging (`structlog`), never bare `print` in `src/`.
- No comment that restates the line below it. Comments explain *why*.
- Small modules. If a file passes ~300 lines, it's probably two ideas.
