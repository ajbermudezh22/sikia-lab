# sikia-lab

Streaming audio in, a structured clinical note out — with the provider layer treated
as unreliable by default.

A small, working implementation of the three pieces that decide whether real-time
medical documentation survives contact with production: a **websocket audio
pipeline**, a **health-aware multi-provider router**, and an **offline LLM-as-judge
eval harness**. It runs with no API keys.

```bash
./scripts/bootstrap.sh     # python 3.12, deps, tests
```

## Why these three pieces

Transcribing a consultation is easy in a demo and hard in a clinic. The hard parts
aren't the models — they're what happens when a provider is slow at 11am on a Tuesday
while a doctor is mid-sentence. So the interesting code here is failure handling:

- **A slow provider is a failed provider.** Every call has a hard timeout tighter
  than the chunk budget. Waiting is not a strategy when the output is meant to be live.
- **Consecutive failures trip a breaker.** A dead provider is taken out of rotation
  instead of being retried on every chunk. After a cooldown, exactly one probe request
  is allowed through, so recovery is automatic but never a thundering herd.
- **A dropped chunk is a gap, not a dead session.** Ending a live consultation is
  worse than a hole in the transcript. Gaps are counted and surfaced to the client.
- **The eval harness weights safety above style.** A hallucinated finding and an
  awkward sentence are not the same category of problem, and a flat average lets good
  prose hide a safety failure. Critical criteria have floors that fail a case outright.

## What the numbers say

```
$ uv run python scripts/bench.py

300 calls per scenario, one 320ms audio chunk each

healthy primary                    p50=  2.40ms  p95=  2.55ms  p99=  2.69ms  failures=0
primary down, failover to backup   p50=  4.83ms  p95=  5.16ms  p99=  5.33ms  failures=0
primary down, breaker open after 3 p50=  2.42ms  p95=  2.68ms  p99=  4.38ms  failures=0
primary hangs, 50ms timeout        p50= 52.88ms  p95= 53.28ms  p99= 53.42ms  failures=0
```

Failover roughly doubles latency while it's happening. The breaker turns that from a
per-call tax into a one-time cost. A *hung* provider is the expensive case — the
timeout becomes a floor on p99, which is exactly why it's set below the chunk duration
rather than at some comfortable-sounding 30s.

## Layout

| Path | What's in it |
|---|---|
| `src/sikia_lab/transport.py` | FastAPI app, websocket ingest, session lifecycle |
| `src/sikia_lab/pipeline.py` | Audio chunking, transcription, note generation |
| `src/sikia_lab/router.py` | Failover, circuit breaking, health tracking |
| `src/sikia_lab/providers/` | One narrow protocol; adapters own their own mess |
| `src/sikia_lab/eval/` | Judge harness, weighted rubrics with safety floors |
| `tests/test_router.py` | The interesting tests — every one is a failure scenario |
| `scripts/bench.py` | Latency under failover |

## Running it

```bash
# dev server
.venv/bin/python -m uvicorn sikia_lab.transport:app --reload

# health of every provider in the pool
curl -s localhost:8000/healthz | jq

# tests + lint
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

Providers run in `fake` mode unless keys are present, so a fresh clone runs and tests
green with no credentials. The fakes aren't throwaway mocks — they model slowness,
hard failures, and recovery, which is what the router tests actually exercise:

```python
# tests/test_router.py
primary = FakeSTT("primary", priority=0, fail_after=0, recover_after=3)
```

Set `SIKIA_PROVIDER_MODE=live` and add keys from `.env.example` for real calls.

### Websocket protocol

Binary frames are audio (16kHz mono PCM). Text frames are control. Anything else is
ignored rather than fatal — a client bug shouldn't end a consultation.

```
→ <binary audio>     ← {"type":"partial","text":…,"confidence":…,"provider":…}
                     ← {"type":"gap","reason":"all_providers_failed"}
→ "finalize"         ← {"type":"note","text":…,"segments":N,"dropped_chunks":N}
```

## Deploying

```bash
./scripts/deploy_cloudrun.sh
```

Builds with Cloud Build, pushes to Artifact Registry, deploys to Cloud Run in
`europe-west3` (Frankfurt — EU data residency is not optional for this domain).
Request timeout is set to 3600s because Cloud Run holds websockets open for the
duration of the request. `PROJECT_ID` and `REGION` are overridable via environment.

CI runs lint, tests, the benchmark as a regression smoke test, and a Docker build on
every push.

## Reading other codebases

`workspace/` is gitignored scratch space for cloning a repo in to read it:

```bash
./scripts/clone_target.sh git@github.com:org/repo.git
```

The `.claude/` directory carries the workflow for this — `/case-study` runs a
structured onboarding pass (shape → trace one request end-to-end → find the seams →
cited findings), `/trace` walks a single path, and `/present` turns findings into
something speakable. Two subagents, `seam-scanner` and `test-archaeologist`, handle
the fan-out reads. Every finding has to carry a `file.py:line` citation or be labeled
unverified.
